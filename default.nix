{ pkgs ? import ./nixpkgs.nix {} }:

with pkgs;

let
in
{
  py313 = stdenv.mkDerivation rec {
    name = "python313-with-pytest";

    buildInputs = [
      cacert
      git
      gnumake
      openssh
      python313Full
      python313Packages.pytest
      python313Packages.tkinter
    ];
  };

  py312 = stdenv.mkDerivation rec {
    name = "python312-with-pytest";

    buildInputs = [
      cacert
      git
      gnumake
      openssh
      python312Full
      python312Packages.pytest
      python312Packages.tkinter
    ];
  };
 
  py311 = stdenv.mkDerivation rec {
    name = "python311-with-pytest";

    buildInputs = [
      cacert
      git
      gnumake
      openssh
      python311Full
      python311Packages.pytest
      python311Packages.tkinter
    ];
  };

  py310 = stdenv.mkDerivation rec {
    name = "python310-with-pytest";

    buildInputs = [
      cacert
      git
      gnumake
      openssh
      python310Full
      python310Packages.pytest
      python310Packages.tkinter
    ];
  };

  py39 = stdenv.mkDerivation rec {
    name = "python39-with-pytest";

    buildInputs = [
      cacert
      git
      gnumake
      openssh
      python39Full
      python39Packages.pytest
      python39Packages.tkinter
    ];
  };
}
