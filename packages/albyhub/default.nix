{ lib
, buildGoModule
, fetchFromGitHub
, stdenv
}:

buildGoModule (finalAttrs: {
  pname = "albyhub";
  version = "1.24.0";

  src = fetchFromGitHub {
    owner = "getAlby";
    repo = "hub";
    tag = "v${finalAttrs.version}";
    hash = "sha256-IC3rl/9aJ88GgvGfhcJb1/pQb3xIkhYih1hLPJ8itP8=";
  };

  vendorHash = "sha256-A4OsntoJUDkvWJxnZFFxw5AjUPmwRl764nQ5FEA2yeo=";

  patches = [
    ./0001-private-route-hints.patch
    ./0003-loopback-bind-host.patch
    ./0004-lnd-only.patch
    ./0005-no-frontend.patch
  ];

  # LND-only, no-frontend build: the only native dependency needed for
  # cgo (sqlite3) is the C/C++ runtime from stdenv.cc.cc. No nodejs/yarn
  # (no frontend), no bark-ffi-go or ldk-node (removed backends).
  buildInputs = [
    (lib.getLib stdenv.cc.cc)
  ];

  subPackages = [
    "cmd/http"
  ];

  ldflags = [
    "-X github.com/getAlby/hub/version.Tag=v${finalAttrs.version}"
    "-s"
    "-w"
  ];

  postInstall = ''
    mv $out/bin/http $out/bin/albyhub
  '';

  meta = {
    description = "Control lightning wallets over nostr";
    homepage = "https://github.com/getAlBy/hub";
    license = lib.licenses.asl20;
    platforms = lib.platforms.linux;
    mainProgram = "albyhub";
  };
})
