{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.targets.darwin.dock;
  reconciler = pkgs.callPackage ./reconciler/package.nix {};

  statePath = "darwin-dock-applications";

  apps = pkgs.runCommandLocal "home-manager-darwin-dock-applications" { } ''
    for applicationName in ${lib.escapeShellArgs cfg.apps}; do
      application="${config.home.path}/Applications/$applicationName"

      if [[ ! -e "$application" ]]; then
        echo "Application '$applicationName' was not found in \`config.home.path\`" >&2
        exit 1
      fi

      echo "$applicationName"
    done | sort -u > "$out"
  '';
in
{
  options.targets.darwin.dock = {
    enable = lib.mkEnableOption "managing macOS Dock applications";

    apps = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [
        "Zed.app"
        "Spotify.app"
      ];
      description = ''
        Application bundles to add to the Dock. The bundles must be provided by
        <option>home.packages</option>.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      (lib.hm.assertions.assertPlatform "targets.darwin.dock" pkgs lib.platforms.darwin)
    ];

    home = {
      extraBuilderCommands = ''
        ln -s ${apps} "$out/${statePath}"
      '';

      activation.dockApplications = lib.hm.dag.entryAfter [ "installPackages" ] ''
        oldHomePath=/var/empty
        oldApplications=/dev/null
        newHomePath="$newGenPath/home-path"
        newApplications="$newGenPath/${statePath}"

        # Older generations did not record the applications managed in the Dock.
        if [[ -v oldGenPath && -f "$oldGenPath/${statePath}" ]]; then
          oldApplications="$oldGenPath/${statePath}"
          oldHomePath="$oldGenPath/home-path"
        fi

        dockPlist="${config.home.homeDirectory}/Library/Preferences/com.apple.dock.plist"

        if [[ ! -f "$dockPlist" ]]; then
          warnEcho "Could not find the macOS Dock preferences. Skipping Dock updates."
        else
          dryRun=()
          restartDock=()
          if [[ -v DRY_RUN ]]; then
            dryRun=(--dry-run)
          elif [[ "$(/bin/launchctl managername)" == Aqua ]]; then
            restartDock=(--restart-dock)
          fi

          if ! run ${lib.getExe' reconciler "reconcile"} \
            --dock-plist "$dockPlist" \
            --old-applications "$oldApplications" \
            --new-applications "$newApplications" \
            --old-home-path "$oldHomePath" \
            --new-home-path "$newHomePath" \
            "''${dryRun[@]}" \
            "''${restartDock[@]}"; then
            exit 1
          fi
        fi
      '';
    };
  };
}
