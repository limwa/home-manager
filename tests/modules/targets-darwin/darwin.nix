{ pkgs, ... }:
let
  darwinTestApp = pkgs.runCommandLocal "target-darwin-example-app" { } ''
    mkdir -p $out/Applications/example.app/Contents $out/Applications/other.app/Contents
    touch $out/Applications/example.app/Contents/Info.plist $out/Applications/other.app/Contents/Info.plist
  '';

  dockReconciler = pkgs.writers.writePython3 "dock-reconciler-test" { } (
    builtins.readFile ../../../modules/targets/darwin/dock/dock.py
  );

  dockReconcilerTest = pkgs.runCommandLocal "dock-reconciler-test" { } ''
    ${
      pkgs.writers.writePython3 "run-dock-reconciler-test" { } (builtins.readFile ./dock-reconciler.py)
    } ${dockReconciler}
    touch $out
  '';
in
{
  config = {
    home.packages = [ darwinTestApp ];
    home.checks = [ dockReconcilerTest ];

    targets.darwin.dock = {
      enable = true;
      apps = [
        "example.app"
        "other.app"
      ];
    };

    nmt.script = ''
      assertFileRegex activate 'rsync.*--links.*--delete'
      assertFileRegex activate 'home-manager-applications/Applications/'
      assertFileContains darwin-dock-applications 'example.app'
      assertFileContains darwin-dock-applications 'other.app'
      assertFileRegex activate 'home-manager-dock-reconciler'
      assertFileRegex activate '[-][-]restart-dock'
    '';
  };
}
