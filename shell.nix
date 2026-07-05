{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    pkgs.python3
    pkgs.python3Packages.pip
    pkgs.stdenv.cc.cc.lib
    pkgs.zlib
    pkgs.zstd
    pkgs.libgcc
  ];

  shellHook = ''
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:${pkgs.zstd}/lib:${pkgs.libgcc.lib}/lib:$LD_LIBRARY_PATH"
    if [ ! -d .venv ]; then
      echo "Creating virtualenv..."
      python3 -m venv .venv
      .venv/bin/pip install --quiet flask maigret pandas
      .venv/bin/pip install --quiet -e sherlock/
    fi
    source .venv/bin/activate
  '';
}

