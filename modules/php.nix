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

let
	phpBase = pkgs.php85;

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

