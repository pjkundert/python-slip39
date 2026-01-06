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
          pytest
          pip
          tkinter
          coincurve scikit-learn scikit-build cmake
          pycryptodome
          pynacl
        ]);

        python39Env  = mkPythonEnv pkgs.python39;
        python310Env = mkPythonEnv pkgs.python310;
        python311Env = mkPythonEnv pkgs.python311;
        python312Env = mkPythonEnv pkgs.python312;
        python313Env = mkPythonEnv pkgs.python313;
        python314Env = mkPythonEnv pkgs.python314;
        python3Env   = mkPythonEnv pkgs.python3;
        pypy310Env   = mkPythonEnv pkgs.pypy310;
        pypy3Env     = mkPythonEnv pkgs.pypy3;

        # Common build inputs for all dev shells
        commonInputs = with pkgs; [
          # Common tools
          cacert
          git
          gnumake
          openssh
          bash
          bash-completion
          which

          # coincurve + skikit-learn requires this to build:
          cmake clang ninja pkg-config

          # Utilities for creating MacOS .dmg
          nodejs_20     # Not a bleeding-edge version
        ];

        commonShellHook = ''
          echo "Welcome to the Crypto Licensing multi-Python development environment!"
          echo "Available Python interpreters:"
          echo ""
          for cmd in python python3.9 python3.10 python3.11 python3.12 python3.13 python3.14 pypy3 pypy3.10; do
            printf "%-12s: %-20.19s: %s\n" "$cmd" "$($cmd --version 2>/dev/null || echo "(unavailable)")" "$(which $cmd 2>/dev/null)"
          done
          echo ""
          echo "All versions have pytest, pip, tkinter, coincurve, pycryptodome, and pynacl installed."
          echo "Use 'make test' to run tests with the default Python version."
        '';

        # Create a dev shell with specific Python environment(s) and optional extras
        mkDevShell = { pythonEnvs, extraInputs ? [], shellHook ? commonShellHook}: pkgs.mkShell {
          buildInputs = commonInputs ++ pythonEnvs ++ extraInputs;
          inherit shellHook;
        };
      in {
        # Single development shell with all Python versions
        devShells.default = mkDevShell {
          pythonEnvs = [ python3Env ];
        };

        # Individual development shells for specific Python versions
        devShells.py39 = mkDevShell {
          pythonEnvs = [ python39Env ];
        };

        devShells.py310 = mkDevShell {
          pythonEnvs = [ python310Env ];
        };

        devShells.py311 = mkDevShell {
          pythonEnvs = [ python311Env ];
        };

        devShells.py312 = mkDevShell {
          pythonEnvs = [ python312Env ];
        };

        devShells.py313 = mkDevShell {
          pythonEnvs = [ python313Env ];
        };

        devShells.py314 = mkDevShell {
          pythonEnvs = [ python314Env ];
        };

        devShells.py3 = mkDevShell {
          pythonEnvs = [ python3Env ];
        };

        devShells.pypy310 = mkDevShell {
          pythonEnvs = [ pypy310Env ];
        };

        devShells.pypy3 = mkDevShell {
          pythonEnvs = [ pypy3Env ];
        };
      });
}
