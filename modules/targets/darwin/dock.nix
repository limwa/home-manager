{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.targets.darwin.dock;

  appManifest = pkgs.runCommandLocal "home-manager-darwin-dock-app-manifest" { } ''
    for applicationName in ${lib.escapeShellArgs cfg.apps}; do
      application="${config.home.path}/Applications/$applicationName"

      if [[ ! -e "$application" ]]; then
        echo "Application '$applicationName' was not found in \`config.home.path\`" >&2
        exit 1
      fi

      echo "$applicationName"
    done | sort -u > "$out"
  '';

  manifestPath = "darwin-dock-app-manifest";
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
        ln -s ${appManifest} "$out/${manifestPath}"
      '';

      extraActivationPath = [
        pkgs.dockutil
      ];

      activation.dockApplications = lib.hm.dag.entryAfter [ "installPackages" ] ''
        oldApplications=/var/empty
        oldAppManifest=/dev/null
        newApplications="$newGenPath/home-path/Applications"
        newAppManifest="$newGenPath/${manifestPath}"

        # Older generations did not record the applications managed in the Dock.
        if [[ -v oldGenPath && -f "$oldGenPath/${manifestPath}" ]]; then
          oldApplications="$oldGenPath/home-path/Applications"
          oldAppManifest="$oldGenPath/${manifestPath}"
        fi

        dockPlist="${config.home.homeDirectory}/Library/Preferences/com.apple.dock.plist"

        if [[ ! -f "$dockPlist" ]]; then
          warnEcho "Could not find the macOS Dock preferences. Skipping Dock updates."
        else
          dockWasModified=false

          addApplication() {
            local application="$1"
            local applicationLabel="$2"

            # dockutil errors when --replacing does not match an existing item.
            if dockutil --find "$applicationLabel" "$dockPlist" > /dev/null; then
              run dockutil --add "$application" --replacing "$applicationLabel" --no-restart "$dockPlist"
            else
              run dockutil --add "$application" --no-restart "$dockPlist"
            fi

            dockWasModified=true
          }

          while IFS= read -r applicationName; do
            oldApplication="$(readlink -e "$oldApplications/$applicationName")"
            
            # dockutil returns an error when the application was removed manually.
            if dockutil --find "$oldApplication" "$dockPlist" > /dev/null; then
              run dockutil --remove "$oldApplication" --no-restart "$dockPlist"
              dockWasModified=true
            fi
          done < <(comm -23 "$oldAppManifest" "$newAppManifest")

          while IFS= read -r applicationName; do
            newApplication="$(readlink -e "$newApplications/$applicationName")"
            addApplication "$newApplication" "''${applicationName%.app}"
          done < <(comm -13 "$oldAppManifest" "$newAppManifest")

          while IFS= read -r applicationName; do
            oldApplication="$(readlink -e "$oldApplications/$applicationName")"
            newApplication="$(readlink -e "$newApplications/$applicationName")"

            if [[ "$oldApplication" != "$newApplication" ]]; then
              addApplication "$newApplication" "''${applicationName%.app}"
            fi
          done < <(comm -12 "$oldAppManifest" "$newAppManifest")

          if [[ ! -v DRY_RUN && "$dockWasModified" == true && "$(/bin/launchctl managername)" == Aqua ]]; then
            run /usr/bin/killall Dock
          fi
        fi
      '';
    };
  };
}
