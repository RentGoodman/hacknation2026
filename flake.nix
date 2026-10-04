{
  description = "Parcel pipeline development environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "aarch64-linux" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShellNoCC {
            packages = [ pkgs.python312 pkgs.nodejs_24 pkgs.git pkgs.uv ];
            LD_LIBRARY_PATH = pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isLinux
              (pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.zlib ]);
            UV_PYTHON = "${pkgs.python312}/bin/python3";
            UV_PYTHON_DOWNLOADS = "never";
            shellHook = ''
              parcel_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
              UV_PROJECT_ENVIRONMENT="$parcel_root/.venv" \
                uv sync --project "$parcel_root" --frozen || exit $?
              source "$parcel_root/.venv/bin/activate"
              export PYTHONPATH="$parcel_root/extraction/src:$parcel_root''${PYTHONPATH:+:$PYTHONPATH}"
              export PARCEL_PYTHON="$parcel_root/.venv/bin/python3"
              export PYTHONNOUSERSITE=1
              unset parcel_root
            '';
          };
        });
    };
}
