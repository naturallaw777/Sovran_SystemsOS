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

    # postPatch runs in the npmDeps fetcher too. Copy the lock file to
    # the repo root so prefetch-npm-deps can find it, then apply patches
    # in the main build.
    # Also create a dummy rust-gbt stub so `npm ci --offline` can resolve
    # the `file:./rust-gbt` dependency before the real native module is
    # synced in buildPhase.
    postPatch = ''
      cp backend/package-lock.json .
      patch -p1 < ${./0001-allow-disabling-mining-pool-fetching.patch}
      mkdir -p backend/rust-gbt
      cat > backend/rust-gbt/package.json <<'EOF'
      {"name":"rust-gbt","version":"0.0.1","main":"index.js"}
      EOF
    '';

    npmDepsHash = "sha256-tuMrdc9vw5CWzaL1xRxZnskgGwElWv8qz4LSNvSUdXI=";
    npmDepsFetcherVersion = 2;
    makeCacheWritable = true;
    npmFlags = [ "--legacy-peer-deps" ];

    nativeBuildInputs = [
      makeWrapper
      rsync
    ];

    dontNpmBuild = true;
    dontNpmInstall = true;

    buildPhase = ''
      runHook preBuild

      cd backend
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
  mkFrontend = config: buildNpmPackage {
    pname = "mempool-frontend";
    inherit version src;

    # postPatch runs in the npmDeps fetcher too. Copy the lock file to
    # the repo root so prefetch-npm-deps can find it.
    postPatch = ''
      cp frontend/package-lock.json .
    '';

    npmDepsHash = "sha256-/UwK0X9knsqTSAmnh2+jk35SK/J7DjBUhsR7e6OOn8Y=";
    npmDepsFetcherVersion = 2;

    nativeBuildInputs = [
      makeWrapper
      rsync
    ];

    dontNpmBuild = true;
    dontNpmInstall = true;

    buildPhase = ''
      runHook preBuild

      cd frontend
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
