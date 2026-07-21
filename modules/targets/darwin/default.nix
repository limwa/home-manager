{
  lib,
  ...
}:

{
  meta.maintainers = with lib.maintainers; [ midchildan ];

  imports = [
    ./user-defaults
    ./dock.nix
    ./fonts.nix
    ./keybindings.nix
    ./copyapps.nix
    ./linkapps.nix
    ./search.nix
    ./terminfo.nix
  ];
}
