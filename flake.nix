{
  description = "Python slip39 development environment with multiple Python versions";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/16c7794d0a28b5a37904d55bcca36003b9109aaa";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        
        # Create Python environments with required packages
        mkPythonEnv = pythonPkg: pythonPkg.withPackages (ps: with ps; [
          tkinter
          pytest
          #coincurve scikit-learn scikit-build cmake
          #pycryptodome
          #pynacl
        ]);

        python310Env = mkPythonEnv pkgs.python310;
        python311Env = mkPythonEnv pkgs.python311;
        python312Env = mkPythonEnv pkgs.python312;
        python313Env = mkPythonEnv pkgs.python313;
        python314Env = mkPythonEnv pkgs.python314;
        python3Env = mkPythonEnv pkgs.python3;

      in {
        # Single development shell with all Python versions
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Common tools
            cacert
            git
            gnumake
            openssh
            bash
            bash-completion

            # coincurve + skikit-learn requires this to build:
            #cmake clang ninja pkg-config

            # All Python versions with packages
            #python310Env
            #python311Env
            #python312Env
            python313Env
            #python314Env
            #python3Env

            # Utilities for creating MacOS .dmg
            nodejs_20     # Not a bleeding-edge version
          ];

          shellHook = ''
            echo "Welcome to the multi-Python development environment!"
            echo "Available Python interpreters:"
            echo "  python (default): $(python --version 2>/dev/null || echo 'not available')"
            echo "  python3: $(python3 --version 2>/dev/null || echo 'not available')"
            echo "  python3.10: $(python3.10 --version 2>/dev/null || echo 'not available')"
            echo "  python3.11: $(python3.11 --version 2>/dev/null || echo 'not available')"
            echo "  python3.12: $(python3.12 --version 2>/dev/null || echo 'not available')"
            echo "  python3.13: $(python3.13 --version 2>/dev/null || echo 'not available')"
            echo "  python3.14: $(python3.14 --version 2>/dev/null || echo 'not available')"
            echo ""
            echo "All versions have pytest, coincurve, pycryptodome, and pynacl installed."
          '';
        };
      });
}
