{ config, pkgs, lib, ... }:

# ── Shared PHP for Nextcloud + WordPress ──────────────────────────────────────
#
# One interpreter (with one extension set and one php.ini) is shared by the
# phpfpm-nextcloud and phpfpm-wordpress pools, the Nextcloud cron job and the
# occ / wp-cli helper scripts.  Every consumer must reference
# config.sovran_systemsOS.phpPackage (or /run/current-system/sw/bin/php) so
# that the CLI and the FPM pools always run the *same* PHP.
#
# Version policy (September 2026):
#   • Nextcloud 35 supports PHP 8.3 / 8.4 / 8.5 and recommends 8.5.  Its setup
#     check flags 8.3 as "deprecated since Nextcloud 35" and warns that
#     Nextcloud 36 may require at least 8.4.
#   • WordPress 6.9 / 7.0 fully support PHP 8.4 and 8.5.
#   • PHP 8.3 has been security-only since 2025-12-31; PHP 8.4 leaves active
#     support on 2026-12-31; PHP 8.5 is actively supported until 2027-12-31.
#
# To fall back to PHP 8.4 (nixpkgs' current default `pkgs.php`) change only
# the `phpBase` line below.
#
# Security floor (October 2026):
#   CVE-2026-109618 (RCE via OOM corruption) and CVE-2026-109619 (RCE via
#   stale global state) are critical, unauthenticated flaws in PHP itself,
#   CVSS v4.0 9.2 each, fixed in 8.5.12 / 8.4.27 / 8.3.36 / 8.2.35 on
#   2026-10-21.  PHP-FPM is named as susceptible in both advisories, so the
#   pools below are in scope; updating is the only complete mitigation.
#   nixpkgs bumped php85 in 81513f364091c759812f716cef3c175109d07342 the same
#   day, but the nixpkgs revision this flake pins predates it, so the floor is
#   enforced here.  Once flake.lock is at or past that commit the `else`
#   branch below stops being taken and can be deleted.

let
	# The first 8.5.x release that carries the fixes above.  Bump only upward.
	phpSecurityFloor = "8.5.12";

	# php-8.5.12.tar.bz2, the same artifact and URL shape nixpkgs' own
	# generic.nix fetches.  Verified against php.net on 2026-10-23.
	phpSourceHash = "sha256-/7YO3EN87WO1E35JhNs3moERxQBJxxFRDYuVgnfvwag=";

	# `.override` (not `overrideAttrs`) on purpose: php85 is a `makeOverridable`
	# buildEnv, so this threads `version`/`phpSrc` into generic.nix while
	# keeping the default extension set.  `overrideAttrs` would keep the new
	# source but drop the extension set, which would silently strip gd, intl,
	# pdo_pgsql and friends out of the pools below.
	phpBase =
		if lib.versionAtLeast pkgs.php85.version phpSecurityFloor then
			pkgs.php85
		else
			pkgs.php85.override {
				version = phpSecurityFloor;
				phpSrc = pkgs.fetchurl {
					url = "https://www.php.net/distributions/php-${phpSecurityFloor}.tar.bz2";
					hash = phpSourceHash;
				};
			};

	custom-php = phpBase.buildEnv {
		# `enabled` is nixpkgs' default extension set.  It already contains every
		# module Nextcloud lists as required or recommended (ctype, curl, dom,
		# fileinfo, gd, intl, mbstring, openssl, posix, session, simplexml,
		# xmlreader, xmlwriter, zip, zlib, pdo_pgsql, pdo_mysql, bcmath, gmp,
		# exif, sodium, sysvsem, pcntl, ...).  OPcache is compiled into PHP >= 8.5
		# and no longer appears as a separate extension.
		extensions = { enabled, all }: enabled ++ (with all; [
			bz2        # Nextcloud: bz2 archive support
			apcu       # Nextcloud: memcache.local  (apc.enable_cli=1 below is mandatory for occ + cron)
			redis      # Nextcloud: memcache.distributed / file locking once a Redis server is configured
			imagick    # Nextcloud: previews + theming (nixpkgs ImageMagick is built with SVG support)
			memcached  # WordPress object-cache plugins (legacy option for Nextcloud)
		]);

		extraConfig = ''
			; ── Error handling (production) ─────────────────────────────────
			display_errors = Off
			display_startup_errors = Off
			log_errors = On

			; ── Limits ──────────────────────────────────────────────────────
			max_execution_time = 10000
			max_input_time = 3000
			memory_limit = 1G
			post_max_size = 3G
			upload_max_filesize = 3G

			; ── OPcache (Nextcloud "Server tuning" recommendations) ─────────
			opcache.enable = 1
			opcache.memory_consumption = 512
			opcache.interned_strings_buffer = 192
			opcache.max_accelerated_files = 20000
			opcache.revalidate_freq = 240
			opcache.save_comments = 1

			; ── APCu ────────────────────────────────────────────────────────
			apc.enable_cli = 1

			; ── phpredis session locking (only used with session.save_handler = redis)
			redis.session.locking_enabled = 1
			redis.session.lock_retries = -1
			redis.session.lock_wait_time = 10000
		'';
	};
in

{
	options.sovran_systemsOS.phpPackage = lib.mkOption {
		type = lib.types.package;
		default = custom-php;
		description = "Shared PHP package with all extensions for Sovran_SystemsOS services";
	};

	config = {
		users.users = {

			php = {
				isSystemUser = true;
				createHome = false;
				uid = 7777;
			};
		};

		users.users.php.group = "php";

		users.groups.php = {};

		environment.systemPackages = with pkgs; [

			custom-php
		];
	};
}

