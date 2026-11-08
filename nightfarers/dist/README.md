# Nightfarers for Elden Ring

Play Nightreign's Wylder in Elden Ring. This is version 0.1, and Wylder is the only hero so far.

- **Wylder as a starting class.** He's the 13th class on the character creation screen, with his own stats, armour, greatsword and shield.
- **Skill: Claw Shot.** Press **Y + LT** (Triangle + L2). It pulls small enemies to you and pulls you to large ones.
- **Ultimate: Onslaught Stake.** Press **Y + RT** (Triangle + R2).
- **Passive: Sixth Sense.**
- **Movement and HUD from Nightreign.** You get Nightreign's movement and skill/ultimate icons, Wylder's own sounds, and no fall damage.

You don't need to own Nightreign. Only Elden Ring runs.

## What you need

1. **Elden Ring on Steam (Windows).** This version was built and tested on Elden Ring **App Ver. 1.17.2** (shown at the bottom right of the title screen). Other patches may not work.
2. **A controller.** The skill and the ultimate are only bound to controller buttons for now. Keyboard players can't use them yet.
3. **me3**, the mod loader. Get it from https://github.com/garyttierney/me3/releases: download the Windows installer (`me3_installer.exe`) and run it. Tested with me3 0.13.0.
4. **ERSoundBankLoader (optional).** You only need it for Wylder's own sounds. It's someone else's mod, so it isn't included here. Download it from GitHub: https://github.com/KamiyamaShiki0704/ERSoundBankLoader/releases. Under the release, open **Assets** and download the zip. Nightfarers was tested with v0.3.0. Without it, everything works except Wylder's sounds.

## Install

1. Unzip this folder anywhere, for example `Documents\Nightfarers`. Don't put it inside the Elden Ring game folder.
2. Install me3 (see above).
3. Optional, for sounds: open the ERSoundBankLoader zip and copy only `er_sound_bank_loader.dll` into `Nightfarers\native\sound_loader\`. You don't need its `.ini` file, because the launcher writes its own.
4. Make sure Steam is running.
5. Double-click **`launch_nightfarers.bat`**.

The game starts with only this mod loaded, offline. On the main menu, choose **New Game** and pick **Wylder** as your class. He's the last entry on the list.

## Your saves are safe

The mod uses its own save file, `NF0000.sl2`. It never touches your normal save (`ER0000.sl2`), so your regular characters stay where they are and you start fresh. Both saves are in `%APPDATA%\EldenRing\<your Steam ID>\`.

## Offline only

The launcher always starts the game offline, with Easy Anti-Cheat off (me3 does this). **Don't try to play online with this mod.** To play online, close the game and start Elden Ring normally from Steam.

## Controls

| Action | Controller |
|---|---|
| Claw Shot (skill) | Y + LT  /  Triangle + L2 |
| Onslaught Stake (ultimate) | Y + RT  /  Triangle + R2 |
| Crouch / stand | Y + L3  /  Triangle + L3 |
| Surge Sprint | L3 |
| Unstuck (if you're stuck in a pit) | Hold L3 + R3 for 2 seconds |

## Doesn't work with other overhaul mods

Nightfarers replaces the game's `regulation.bin` (all item and character data) and the player character's animations. Don't combine it with other mods that change those files, such as large overhauls or other moveset mods. The launcher loads only Nightfarers, so the mods you already have are left alone and stay off while you play this.

## Uninstall

Delete the `Nightfarers` folder. If you also want to remove your Nightfarers character, delete `NF0000.sl2` (and `NF0000.sl2.bak`) from `%APPDATA%\EldenRing\<your Steam ID>\`.

## Troubleshooting

- **"me3 was not found".** Install me3 with its Windows installer and run the launcher again. If you'd rather use the portable zip, unzip it into `Nightfarers\me3\`, so the file sits at `Nightfarers\me3\bin\me3.exe`.
- **The game doesn't start, or crashes on launch.** Check that Steam is running and that Elden Ring is up to date. Look at the message in the launcher window.
- **Wylder isn't on the class screen.** The mod didn't load. Start the game with `launch_nightfarers.bat`, not from Steam.
- **No Wylder sounds.** Check that `er_sound_bank_loader.dll` is in `native\sound_loader\`. After a launch, that folder also holds the sound loader's log.
- **Something else is wrong.** `native\nightfarers_native.log` (written on every launch) shows what the mod did. Include it when you report a bug.

## Files

- `launch_nightfarers.bat` starts the game. It writes `nightfarers.me3` (the me3 profile) on each launch, and the sound loader's settings too if the sound loader is installed.
- `package\` holds the game data: Wylder's model, animations, effects, sounds, menus and text.
- `native\nightfarers_native.dll` handles the button combos, Claw Shot, Onslaught Stake, Sixth Sense, the HUD and unstuck.

## Credits

- Elden Ring and Elden Ring Nightreign by FromSoftware / Bandai Namco. Wylder and his assets are theirs. This is a free fan mod, not affiliated with them.
- me3 by garyttierney and contributors.
- ERSoundBankLoader by KamiyamaShiki0704 (not included): https://github.com/KamiyamaShiki0704/ERSoundBankLoader
- Built with help from Claude (AI).
