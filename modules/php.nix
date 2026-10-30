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
# To fall back to PHP 8.4, change only the `phpBase` line below (and drop the
# security floor to the matching 8.4.x release).
#
# Security floor (October 2026):
#   CVE-2026-109618 (RCE via OOM corruption) and CVE-2026-109619 (RCE via
#   stale global state) are critical, unauthenticated flaws in PHP itself,
#   CVSS v4.0 9.2 each, fixed in 8.5.12 / 8.4.27 / 8.3.36 / 8.2.35 on
#   2026-10-21.  PHP-FPM is named as susceptible in both advisories, so the
#   pools below are in scope; updating is the only complete mitigation.
#
#   nixpkgs bumped php85 to 8.5.12 in 81513f364091c759812f716cef3c175109d07342
#   and fixed the `filter` extension tests in
#   a5fc1be5b6c2d0c934143b57363aef9a15cce508.  flake.lock pins nixpkgs as
#   nixpkgs_2 = 31ecbaca1bdefa45dffc409f0250bd8039ea0010, which is *after*
#   both of them.  (The `nixpkgs` node in flake.lock, a8e753600fb4, is
#   btc-clients' input and only builds bisq/sparrow — do not audit it for
#   system packages.)  Verified at that rev:
#   pkgs/development/interpreters/php/default.nix says php85 = 8.5.12, and
#   pkgs/top-level/php-packages.nix already carries the oom_filter_*.phpt
#   patch.  So the stock package is used as-is and the floor below is only an
#   assertion that catches a rolled-back pin.
#
#   Do NOT re-apply the `filter` test fix locally.  It uses
#       --replace-fail "'-n'," "'-n', '-d', 'extension=$PWD/modules/filter.so',"
#   and the replacement text still contains the `'-n',` it searches for, so a
#   second application silently injects `-d extension=.../filter.so` twice.
#   PHP then emits `Module "filter" is already loaded` (Zend/zend_API.c,
#   E_CORE_WARNING) into the php-cgi output the tests capture, all three
#   oom_filter_*.phpt fail on the unexpected line, `make test` exits non-zero
#   and the builder dies with exit code 2 — the exact failure the patch was
#   meant to prevent.

let
	# The first 8.5.x release that carries the fixes above.  Bump only upward.
	phpSecurityFloor = "8.5.12";

	# Stock nixpkgs package: correct version, correct extension recipes and
	# upstream's own test fixes.  `.override { version = ...; phpSrc = ...; }`
	# is deliberately *not* used here — rewriting the version while keeping the
	# extension recipes of another release is how you end up with test (or
	# ABI) failures that look like packaging bugs.
	phpBase = pkgs.php85;

	custom-php = phpBase.buildEnv {
		# `enabled` is nixpkgs' default extension set.  It already contains every
		# module Nextcloud lists as required or recommended (ctype, curl, dom,
		# fileinfo, gd, intl, mbstring, openssl, posix, session, simplexml,
		# xmlreader, xmlwriter, zip, zlib, pdo_pgsql, pdo_mysql, bcmath, gmp,
		# exif, sodium, sysvsem, pcntl, filter, ...).  OPcache is compiled into
		# PHP >= 8.5 and no longer appears as a separate extension.
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
		# Security floor.  This has to live in `config.assertions`, NOT in a
		# module-level `assert` above the module body: a bare
		# `assert <cond>; { ... }` forces `phpBase` (and therefore `pkgs`) as
		# soon as the module's attrset is forced to WHNF, which happens while
		# the module system is still merging `_module.args`.  `pkgs` is not an
		# externally supplied argument here, so it resolves through
		# `config._module.args.pkgs` (lib/modules.nix:745) — which requires
		# `config`, the very fixpoint being computed — giving
		# "error: infinite recursion encountered" pointing at modules/php.nix.
		# `config.assertions` is evaluated inside the fixpoint, once `pkgs`
		# exists, which is the supported way to assert on package versions.
		assertions = [
			{
				assertion = lib.versionAtLeast phpBase.version phpSecurityFloor;
				message = ''
					sovran_systemsOS: the pinned nixpkgs ships PHP ${phpBase.version},
					below the security floor ${phpSecurityFloor} (CVE-2026-109618 /
					CVE-2026-109619).  Update the nixpkgs input in flake.lock instead
					of pinning a version in modules/php.nix.
				'';
			}
		];

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
