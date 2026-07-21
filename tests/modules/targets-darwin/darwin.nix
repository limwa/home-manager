{ pkgs, ... }:
let
  darwinTestApp = pkgs.runCommandLocal "target-darwin-example-app" { } ''
    mkdir -p $out/Applications/example.app
  '';
in
{
  config = {
    home.packages = [ darwinTestApp ];

    nmt.script = ''
      assertFileRegex activate 'rsync.*--links.*--delete'
      assertFileRegex activate 'home-manager-applications/Applications/'
    '';
  };
}
