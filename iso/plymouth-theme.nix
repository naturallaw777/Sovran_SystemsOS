{ pkgs, lib }:

pkgs.stdenv.mkDerivation {
  pname = "sovran-plymouth-theme";
  version = "1.0";

  src = ./.;

  installPhase = ''
    mkdir -p $out/share/plymouth/themes/sovran
    cp ${./assets/splash-logo.png} $out/share/plymouth/themes/sovran/logo.png

    cat > $out/share/plymouth/themes/sovran/sovran.plymouth <<EOF
[Plymouth Theme]
Name=Sovran Systems
Description=Sovran Systems Splash
ModuleName=script

[script]
ImageDir=$out/share/plymouth/themes/sovran
ScriptFile=$out/share/plymouth/themes/sovran/sovran.script
EOF

    cat > $out/share/plymouth/themes/sovran/sovran.script <<'EOF'
# Background color: #CFFFD7 (RGB 207,255,215)
bg_r = 207/255.0
bg_g = 255/255.0
bg_b = 215/255.0

Window.SetBackgroundTopColor (bg_r, bg_g, bg_b);
Window.SetBackgroundBottomColor (bg_r, bg_g, bg_b);

logo = Image("logo.png");
logo_sprite = Sprite(logo);
logo_sprite.SetX((Window.GetWidth() - logo.GetWidth()) / 2);
logo_sprite.SetY((Window.GetHeight() - logo.GetHeight()) / 2);
EOF
  '';
}