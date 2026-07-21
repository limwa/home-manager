{
  mkShell,
  python3,
}:

python3.pkgs.buildPythonApplication (finalAttrs: {
  pname = "home-manager-darwin-dock-reconciler";
  version = "0.0.1";

  src = ./.;

  format = "pyproject";

  build-system = with python3.pkgs; [
    hatchling
  ];

  dependencies = with python3.pkgs; [
    pydantic
  ];

  passthru.devShell = mkShell {
    name = "home-manage-darwin-dock-reconciler-devshell";
    inputsFrom = [ finalAttrs.finalPackage ];
  };
})