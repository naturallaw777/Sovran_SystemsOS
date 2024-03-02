{ lib, stdenv, fetchzip, buildPackages }:

			stdenv.mkDerivation rec {
				pname = "systemd-manager";
				version = "15";

				src = fetchzip {
					url = "https://github.com/hardpixel/systemd-manager/releases/download/v${version}/systemd-manager-v${version}.zip";
					hash = "sha256-IIiHvntAnaEJIiofNDOQXDKeJupyEMys32N8Qz1IfXk=";
					stripRoot = false;
				};

				passthru = {
					extensionUuid = "systemd-manager@hardpixel.eu";
					extensionPortalSlug = "systemd-manager";
				};

				nativeBuildInputs = [ buildPackages.glib ];

				buildPhase = ''
					runHook preBuild
					if [ -d schemas ]; then
						glib-compile-schemas --strict schemas
					fi
					runHook postBuild
				'';

				installPhase = ''
					runHook preInstall
					mkdir -p $out/share/gnome-shell/extensions
					 cp -r -T . $out/share/gnome-shell/extensions/${passthru.extensionUuid}
					runHook postInstall
				'';

				meta = with lib; {
					description = "GNOME Shell extension to manage systemd services";
					license = licenses.gpl2Plus;
					maintainers = with maintainers; [ ];
					homepage = "https://github.com/hardpixel/systemd-manager";
				};
			}