{ lib
, buildNpmPackage
, nodejs_22
, nodejs-slim_22
, fetchurl
, makeWrapper
}:

let
  version = "0.15.8";

  src = fetchurl {
    url = "https://github.com/Ride-The-Lightning/RTL/archive/refs/tags/v${version}.tar.gz";
    hash = "sha256-8XdGyORxB2dkZRB/Yl7zh+Quqo4L/Y0VmC6Brbr/hqU=";
  };

in buildNpmPackage {
  pname = "rtl";
  inherit version src;

  # Placeholder: build once, then replace with the hash from the
  # "hash mismatch" error output.
  npmDepsHash = "sha256-hNBPdIBTHkAQ0Kztj9xvBEqYIkFW8mLZ3W6LAwYPOqM=";

  npmFlags = [ "--legacy-peer-deps" ];

  nativeBuildInputs = [
    makeWrapper
  ];

  dontNpmBuild = true;
  dontNpmInstall = true;

  # `src` already contains the precompiled frontend and backend.
  # Copy all files required for packaging, like in
  # https://github.com/Ride-The-Lightning/RTL/blob/master/dockerfiles/Dockerfile
  installPhase = ''
    dest=$out/lib/node_modules/rtl
    mkdir -p $dest
    cp -r \
      rtl.js \
      package.json \
      frontend \
      backend \
      node_modules \
      $dest

    makeWrapper ${nodejs-slim_22}/bin/node "$out/bin/rtl" \
      --add-flags "$dest/rtl.js"

    runHook postInstall
  '';

  passthru = {
    nodejs = nodejs_22;
    nodejsRuntime = nodejs-slim_22;
  };

  meta = with lib; {
    description = "A web interface for LND";
    homepage = "https://github.com/Ride-The-Lightning/RTL";
    license = licenses.mit;
    maintainers = with maintainers; [ ];
    platforms = platforms.unix;
  };
}
