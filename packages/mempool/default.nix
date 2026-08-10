{ lib
, stdenvNoCC
, nodejs_22
, nodejs-slim_22
, buildNpmPackage
, fetchFromGitHub
, runCommand
, makeWrapper
, curl
, cacert
, rsync
, cargo
, rustc
, rustPlatform
, napi-rs-cli
}:

let
  version = "3.2.1";

  src = fetchFromGitHub {
    owner = "mempool";
    repo = "mempool";
    tag = "v${version}";
    hash = "sha256-O2XPD1/BXQnzuOP/vMVyRfmFZEgjA85r+PShWne0vqU=";
  };

  frontendAssets = stdenvNoCC.mkDerivation {
    name = "mempool-frontend-assets";
    outputHashMode = "recursive";
    outputHashAlgo = "sha256";
    outputHash = "sha256-r6GfOY8Pdh15o2OQMk8syfvWMV6WMCReToAEkQm7tqQ=";
    nativeBuildInputs = [ curl cacert ];
    buildCommand = ''
      mkdir $out
      cd $out
      ${builtins.readFile ./frontend-assets-fetch.sh}
    '';
  };

  mempool-rust-gbt = stdenvNoCC.mkDerivation rec {
    pname = "mempool-rust-gbt";
    inherit version src;

    sourceRoot = "source/rust/gbt";

    nativeBuildInputs = [
      rustPlatform.cargoSetupHook
      cargo
      rustc
      napi-rs-cli
    ];

    cargoDeps = rustPlatform.fetchCargoVendor {
      inherit src;
      name = "${pname}-${version}";
      inherit sourceRoot;
      hash = "sha256-eox/K3ipjAqNyFt87lZnxaU/okQLF/KIhqXrX86n+qw=";
    };

    buildPhase = ''
      runHook preBuild
      # napi doesn't accept an absolute path as dest dir, so we can't directly write to $out
      napi build --platform --release --strip out
      runHook postBuild
    '';

    installPhase = ''
      mv out $out
      cp package.json $out
    '';

    passthru = { inherit cargoDeps; };
  };

  sync = "${rsync}/bin/rsync -a --inplace";

in rec {
  mempool-backend = buildNpmPackage {
    pname = "mempool-backend";
    inherit version src;

    # Use postUnpack (not sourceRoot) so the npmDeps fixed-output
    # derivation hashes the same unpacked tree as the main build.
    postUnpack = ''
      cd source/backend
    '';

    # Placeholder: build once, then replace with the hash from the
    # "hash mismatch" error output.
    npmDepsHash = lib.fakeHash;

    nativeBuildInputs = [
      makeWrapper
      rsync
    ];

    # Apply patches only in the main build, not in the npmDeps fetcher.
    postPatch = ''
      patch -p1 < ${./0001-allow-disabling-mining-pool-fetching.patch}
    '';

    dontNpmBuild = true;
    dontNpmInstall = true;

    buildPhase = ''
      runHook preBuild

      patchShebangs node_modules

      ${sync} ${mempool-rust-gbt}/ rust-gbt
      npm run package

      runHook postBuild
    '';

    installPhase = ''
      mkdir -p $out/lib/mempool-backend
      ${sync} package/ $out/lib/mempool-backend

      makeWrapper ${nodejs-slim_22}/bin/node $out/bin/mempool-backend \
        --add-flags $out/lib/mempool-backend/index.js

      runHook postInstall
    '';

    passthru = {
      nodejs = nodejs_22;
      nodejsRuntime = nodejs-slim_22;
    };

    meta = with lib; {
      description = "Bitcoin blockchain and mempool explorer (backend)";
      homepage = "https://github.com/mempool/mempool/";
      license = licenses.agpl3Plus;
      platforms = platforms.unix;
    };
  };

  mempool-frontend = mkFrontend {};

  # Argument `config` (type: attrset) defines the mempool frontend config.
  # If `{}`, the default config is used.
  # See here for available options:
  # https://github.com/mempool/mempool/blob/master/frontend/src/app/services/state.service.ts
  # (`interface Env` and `defaultEnv`)
  mkFrontend = config: buildNpmPackage {
    pname = "mempool-frontend";
    inherit version src;

    # Use postUnpack (not sourceRoot) so the npmDeps fixed-output
    # derivation hashes the same unpacked tree as the main build.
    postUnpack = ''
      cd source/frontend
    '';

    # Placeholder: build once, then replace with the hash from the
    # "hash mismatch" error output.
    npmDepsHash = lib.fakeHash;

    nativeBuildInputs = [
      makeWrapper
      rsync
    ];

    dontNpmBuild = true;
    dontNpmInstall = true;

    buildPhase = ''
      runHook preBuild

      patchShebangs node_modules

      # sync-assets.js is called during `npm run build` and downloads assets from the
      # internet. Disable this script and instead add the assets manually after building.
      : > sync-assets.js

      ${lib.optionalString (config != {}) ''
        ln -s ${builtins.toFile "mempool-frontend-config" (builtins.toJSON config)} mempool-frontend-config.json
      ''}

      npm run build

      # Add assets that would otherwise be downloaded by sync-assets.js
      ${sync} ${frontendAssets}/ dist/mempool/browser/resources

      runHook postBuild
    '';

    installPhase = ''
      ${sync} dist/mempool/browser/ $out

      runHook postInstall
    '';

    passthru = {
      withConfig = mkFrontend;
      assets = frontendAssets;
    };

    meta = with lib; {
      description = "Bitcoin blockchain and mempool explorer (frontend)";
      homepage = "https://github.com/mempool/mempool/";
      license = licenses.agpl3Plus;
      platforms = platforms.unix;
    };
  };

  mempool-nginx-conf = runCommand "mempool-nginx-conf" {} ''
    ${sync} --chmod=u+w ${./nginx-conf}/ $out
    ${sync} ${src}/production/nginx/http-language.conf $out
  '';
}
