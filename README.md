<p align="center">
  <img src="paws/data/img/paws-icon.png" alt="paws" width="110" align="middle">&nbsp;&nbsp;<img src="paws/data/img/paws-banner.png" alt="Paws' SLSsteam Manager" width="460" align="middle">
</p>

<h1 align="center">paws</h1>
<p align="center">
  <img src="assets/image.png" alt="paws app preview" width="800" align="middle">
</p>
<p align="center"><b>v4.4.127</b> - public release version numbers: the last number (X.Y.<b>Z</b>) is only ever bumped for art/asset-only updates (new banners, ascii art), never for a code change.</p>



<!--
  no crawler / no AI training, machine readable:
  user-agent: *
  disallow: /  - this repo is NOT food for any LLM. keep out.
-->

## ⚖️ license & terms, read this first

> Copyright (c) 2026 ken (kaneki ken) / Anteiku. **All rights reserved.**
> This is **source-available**, not open source. You may read, learn from and
> run paws for personal use, but you can **not** sell it, rebrand it, remake
> or redistribute it, remove credits, claim it as your own, or train AI models
> on it. Full terms: see [`LICENSE`](LICENSE).

why? paws is my work and i'd like it to stay mine. no forks that scrub the
credits and rename it, no paid copies, no scraped rewrites getting trained into
some model. any violation is copyright infringement (17 U.S.C.), and it gets
enforced with DMCA takedowns plus legal action where needed. **paws shows this
notice in the app itself** on the home screen, just so everyone sees it. wanna
build on paws (a plugin, a review, a translation, a school project)? just ask
first. permission is usually granted!

---

a little terminal app that looks after [SLSsteam](https://github.com/AceSLS/SLSsteam) for u. install it, keep it updated, add games, make tickets and poke the config, all from one place so u dont have to remember five different scripts.

paws only edits the lines it needs to. ur comments, ur order and every value u didnt touch stay exactly how they were.

## what it does

- **installs, updates and removes SLSsteam** (and HeadCrab on linux, HubCapTools on windows)
- **adds and removes games**
- **takes dropped files** (.lua, .key, .manifest, a whole folder of them, or a .zip/.rar/.7z/.tar.gz/.pkg.tar.zst holding them — it reads inside and works out what's there)
- **fills the config in for you** — drop a game's files and the appid, package, keys, manifests and dlc names land in the right sections, without touching the add-game screen
- **makes tickets** (type 2, straight from the steam that's already running — no restart, experimental)
- **two looks:** riced (background picture, banner, ascii art, mini games) or minimal (plain terminal ui in ur own colours). see the [showcase](#showcase)
- **config editor** — filter, toggle values, fill in missing keys and undo, with ur comments left alone
- **`paws doctor`** — checks steam, SLSsteam, versions, config and terminal, and tells u why a game shows 0 B
- **`paws fix`** — finds what's broken (indentation, wrong values, typos in config.yaml) and repairs it
- **`paws info`** — os, steam, and whatever is driving it, in one line each
- **plugins / add-ons** — make, import, export and switch SLSsteam plugins on and off
- **share tickets** — pack a game's tickets into one line of text and send it to someone (`paws tickets share` / `take`)
- **shell alias, ascii art gallery, colour blind modes and 4 mini games** (tetris, snake, brick breaker, 2048; riced only)
- **tells u when things finish**
- **updates itself** when u open it (git, fast-forward only, skips if ur offline)

## works with

- **distros:** arch and family (manjaro, endeavouros, cachyos, garuda, blackarch, steamos), debian and family (ubuntu, mint, pop!_os, zorin, kali, parrot, mx), fedora and family (nobara, bazzite, rocky, alma), opensuse, void, gentoo, alpine (steam through flatpak), nixos (needs nix-ld so the python wheels run). image based ones (steamos, bazzite, silverblue) are fine, paws only ever writes to ur home
- **package managers:** pacman (paru / yay for the AUR), apt, dnf, rpm-ostree, zypper, xbps, apk, emerge, and steam from flatpak or snap. paws finds ur steam, works out which package owns SLSsteam and prints the right update or remove line. it never runs those for u
- **desktops:** hyprland, sway, gnome, kde plasma, xfce, cinnamon, mate, lxqt, budgie, cosmic, deepin, wayland or x11. `paws --window` opens the terminal ur desktop ships with (konsole, ptyxis / gnome-terminal / kgx, xfce4-terminal, qterminal, mate-terminal ...) or kitty, foot, alacritty, wezterm, ghostty and friends
- **windows:** 🚧 under construction (see below)
- **terminals:** anything with normal colours. kitty and ghostty also get sharp pictures and the glass background, konsole / foot / wezterm get sharp header pictures where sixel is on, the rest get blocky ones. no nerd font? plain icons

i built and tested it by hand on arch + hyprland + kitty. every other distro and desktop is only covered by the automated tests (and the docs of those distros), i didnt poke at them myself. if something looks off run `paws doctor`, it prints the distro, desktop, terminal, colours, locale and clipboard tool it sees. so if any distro has errors please open an issue and explain it in detail, i can't test them all myself.

> **best with kitty + fish + neovim.** paws works anywhere on the list above, but that combo is what it's built and tuned against: kitty gets u the sharp header picture and the full acrylic-glass background, fish gets the nicest shell alias, and `paws edit` opens config.yaml in neovim if u have it (falls back to nano otherwise). none of it is required, it just looks and feels the best there.

## showcase

two looks, same app. **riced** is the glass background + banner + art, **minimal** is a plain terminal ui in ur own colours. pick one when u install or switch any time in Settings > Type. (the folders are called `gui` and `tui` but both are terminal screens.)

<details>
<summary><b>🖥️ riced look</b> <sub>(click to view)</sub></summary>
<br>

<p align="center">
  <img src="showcase/gui/image.png" alt="gui - startup splash, checks for a newer paws" width="700"><br>
  <sub>startup splash, checks for a newer paws</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(1).png" alt="gui - home menu" width="700"><br>
  <sub>home menu</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(2).png" alt="gui - add a game: search the store" width="700"><br>
  <sub>add a game: search the store</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(3).png" alt="gui - activation: make tickets" width="700"><br>
  <sub>activation: make tickets</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(4).png" alt="gui - colour blind modes" width="700"><br>
  <sub>colour blind modes</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(5).png" alt="gui - settings" width="700"><br>
  <sub>settings</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(6).png" alt="gui - shell alias" width="700"><br>
  <sub>shell alias</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(7).png" alt="gui - arcade / mini games" width="700"><br>
  <sub>arcade / mini games</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(8).png" alt="gui - plugins / add-ons" width="700"><br>
  <sub>plugins / add-ons</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(9).png" alt="gui - config editor" width="700"><br>
  <sub>config editor</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(10).png" alt="gui - install / update / uninstall" width="700"><br>
  <sub>install / update / uninstall</sub>
</p>

<p align="center">
  <img src="showcase/gui/image(11).png" alt="gui - status / doctor" width="700"><br>
  <sub>status / doctor</sub>
</p>

</details>

<details>
<summary><b>⌨️ minimal look</b> <sub>(click to view)</sub></summary>
<br>

<p align="center">
  <img src="showcase/tui/image.png" alt="tui - startup splash" width="700"><br>
  <sub>startup splash</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(1).png" alt="tui - home menu" width="700"><br>
  <sub>home menu</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(2).png" alt="tui - status / doctor" width="700"><br>
  <sub>status / doctor</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(3).png" alt="tui - install / update / uninstall" width="700"><br>
  <sub>install / update / uninstall</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(4).png" alt="tui - add a game: search the store" width="700"><br>
  <sub>add a game: search the store</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(5).png" alt="tui - remove a game" width="700"><br>
  <sub>remove a game</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(6).png" alt="tui - activation: make tickets" width="700"><br>
  <sub>activation: make tickets</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(7).png" alt="tui - config editor" width="700"><br>
  <sub>config editor</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(8).png" alt="tui - plugins / add-ons" width="700"><br>
  <sub>plugins / add-ons</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(9).png" alt="tui - shell alias" width="700"><br>
  <sub>shell alias</sub>
</p>

<p align="center">
  <img src="showcase/tui/image(10).png" alt="tui - settings" width="700"><br>
  <sub>settings</sub>
</p>

</details>

## install

paws needs python 3.9+ and steam. git is only for `paws update`. **one command, no root, any distro:**

    git clone https://github.com/one-eyed-queen/paws
    cd paws
    ./scripts/install.sh

it makes a private python env in `~/.local/share/paws`, links `paws` into `~/.local/bin`, adds the icon + app menu entry and sets up ur shells PATH (fish, zsh or bash). keep the folder u cloned, `paws update` pulls new versions from it. `./scripts/install.sh --dry-run` shows what it would do first.

if it says it cant make an environment, ur distro ships python without the venv module: `sudo apt install python3-venv` (debian, ubuntu, mint, pop, kali, parrot). on steamos, bazzite and other readonly systems it works as is.

pick the look when u install: `./scripts/install.sh --riced` or `--minimal` (the one-liner installer takes the same flags, and both ask if u leave them out). riced is the full thing, background picture, banner, ascii art, mini games, desktop notifications. minimal is a plain terminal ui in ur own colours: no pictures, no mini games, no art, and notifications only inside the app. switch any time in Settings > Type, it applies right away. no steam yet? `paws doctor` prints the install line for ur package manager. `paws desktop` re-adds the icon and app menu entry (`--shortcut` puts one on ur desktop too, or tick it in Settings).

## windows 🚧

**windows works, with one hole in it.** SLSsteam itself is linux only, so on windows paws drives one of its two ports. both are found automatically:

- **HubCapTools** — a steam DLL proxy (`dwmapi.dll` next to `steam.exe`). `paws sls install` fetches the installer from [one-eyed-queen/HubCapTools](https://github.com/one-eyed-queen/HubCapTools), checks it against the sha256 paws has pinned for that build, and runs it. **close steam completely first** — the client keeps what it already loaded, so a dll dropped beside a running `steam.exe` does nothing.
- **OpenValve** — a manager. there is nothing to download and nothing to unpack, so paws never tries: it just reads and writes the config OpenValve already keeps.

<details>
<summary>windows notes (click to open)</summary>

same paws, same menus, same commands. the only thing that changes is where stuff lives:

- **OpenValve's** config: `%AppData%\SLSsteam\config.yaml` (the normal SLSsteam config plus a few extra settings), cache in `%AppData%\SLSsteam\cache`
- **HubCapTools'** config: `<steamdir>\config\hubcaptools`, cache one level down
- paws' own settings, backups and undo journal: `%AppData%\paws`
- steam: found through the registry, so a steam on another drive is fine

paws tells the two apart by where their config lives, so it never has to guess which one u have.

install (no admin, needs python 3.10+ from python.org or `winget install Python.Python.3.12`, and git for `paws update`):

    git clone https://github.com/one-eyed-queen/paws
    cd paws
    powershell -ExecutionPolicy Bypass -File scripts\install.ps1

it makes a private python env in `%LOCALAPPDATA%\paws`, puts `paws` on ur PATH and adds it to the start menu. `-DryRun` shows what it would do first, `-Riced` / `-Minimal` pick the look. best in windows terminal, the old console works too.

what works: config editing, adding / removing games, keys, manifests, tokens, dlc, dropping `.lua` / `.key` / `.manifest` files and bundles, the ticket cache, finding steam, installing / updating / removing HubCapTools, `paws info`, `paws doctor`.

🚧 **the one hole: making tickets.** paws can read both ports' config and cache, but nothing documents how either one hands out type 2 tickets, so `paws activate` says so instead of pretending. everything else about activation works on linux (see below).

paws also **refuses to delete OpenValve's config** on uninstall: it sits in the standard `%AppData%\SLSsteam` spot and paws didn't create it. it removes HubCapTools' dll and its own folder, and tells you which one it left.

#### how to download games

paws does all of this for u when u add a game (drag and drop, add game, or the live fixer), and it checks which SLSsteam u actually have installed first, so it only ever writes settings ur build reads. this is what it writes so u know:

**private build** (reads `DecryptionKeys` and `AdditionalPackageApps` or `AdditionalPackages`), the only one that can download:

1. the depot keys go in `DecryptionKeys:`, one line per key: `appid: "key"`
2. the game goes in `AdditionalPackageApps:` on private builds from 2026-11 (their own docs: "use this instead of AdditionalApps for every game you want to download"). older private builds get the game's store package in `AdditionalPackages:` and its other depots in `AdditionalDepots:` instead
3. the game's base AppId goes in `AppIds:`
4. `UseWhitelist:` is set to `yes` (needed whenever u use AppIds)
5. no `AdditionalApps:` row: it overwrites the owner id and breaks the download

**public build** (github release): it puts games in ur library but **can't download them**, so they show 0 B. that's the build, not ur config. paws writes:

1. the game's AppId in `AdditionalApps:` (that's what makes it show up) and in `AppIds:`
2. the depot keys straight into steam's own `config.vdf` (public SLSsteam has no `DecryptionKeys:`), plus a copy paws keeps so they come back if steam moves or gets reinstalled
3. the `.manifest` files into steam's depotcache, and `ManifestIds:` / `AppTokens:` / `DlcData:` as needed
4. none of the private-only sections (`AdditionalPackageApps`, `AdditionalPackages`, `DecryptionKeys`, `AdditionalDepots`, `CloudProxies`, `InventoryItems`), unless a plugin reads them (below). if ur config has ones nothing reads, the fixer moves their keys out and removes them

**public build + the download plugin** downloads too. `download.lua` is an SLSsteam lua plugin (the one enter-the-wired and ASSella ship) that does what private builds do natively: it puts the game's depots into package 0 so steam counts them as yours, hands steam the keys, and fetches the manifest codes valve refuses. add it with `paws plugins download` or **Plugins > Download plugin** (paws only installs the exact file it checked, by sha256, and never adds it by itself because it runs inside steam). steam can stay open: the plugin loads the next time steam starts. it also turns `DisableUpdates` off, because with it on SLSsteam fails steam's update info for every `AdditionalApps` game, and that's where steam gets a download's size and progress, so the game shows 0 B. then paws writes:

1. the game in `AdditionalApps:` and `AppIds:`, like the plain public build
2. every keyed depot except the game itself in `AdditionalDepots:`, and the keys in `DecryptionKeys:` (the same layout SLSsteam's own convert-lua prints)
3. the keys in `config.vdf`, the manifests in the depotcache, `ManifestIds:` / `AppTokens:` / `DlcData:` as needed

with all that, **Install** shows the game's real size, the download shows its real size and progress, and there's no "no internet connection": steam downloads it like a game u own.

the plugin hooks steam by byte patterns, so a steam update can break it. `paws doctor` checks its patterns against ur `steamclient.so` and says when it doesn't fit any more.

every row gets the game's full name as a comment. `paws doctor` tells u which build u have and why a game is at 0 B.

**"no internet connection" when a download starts** isn't ur internet. steam asks valve for a code for each depot's manifest, valve says "Access Denied" for a game u don't own, and steam shows that as no connection. private builds and the download plugin get that code themselves, the plain public build can't. `paws doctor` reads steam's own download log and tells u which depot it was.

**steam deletes a game u downloaded some other way** (DepotDownloader and friends) at its next start when nothing gives it a license for the depots, so on the plain public build files u put there by hand don't stay. with the download plugin steam downloads and keeps them itself.

**a 64-bit SLSsteam won't load into steam.** the steam client is 32-bit, so a build made for 64-bit gets "wrong ELF class" from the loader and steam starts without it (then it removes the games u don't own). paws refuses to install one and `paws doctor` flags one that's already there.

**Install / Update never swap a private build for the public one by themselves.** github only has the public build, so Update leaves a private one alone and Install asks first. to update a private build, drop its newer .7z on paws.

the private steps are the same on linux and windows; the config format didn't change, so a bundle u drop into a linux install writes exactly what OpenValve expects.

</details>

## installing a build

the install screen is three buttons in one row — **Install**, **Update**, **Uninstall**. hitting **Install** asks which build you want:

- **SLSsteam** → then asks which of the four assets it publishes: **Any** (portable `.7z`) or **Arch** (native pacman package), each in **release** or **debug**. the Arch package is greyed out unless you're on arch and family, and a flavour the release doesn't have is greyed out too
- **HeadCrab** → its own installer, run in your terminal so you can watch it
- **HubCapTools** → fetches, verifies and runs it (windows)
- **OpenValve** → greyed out on linux. on windows picking it just tells you it's a manager with nothing to download, instead of pretending

the builds that can't run on your system stay visible but greyed out with the reason next to them, so you can see the whole family. which ones are greyed comes from the os detector, so it can't disagree with `paws info`.

**Update** and **Uninstall** work the same way, and both say plainly when they did nothing and why, instead of reporting a job that quietly changed nothing.

## what paws looks for

paws works with one family of builds. they are all the same thing underneath **SLSsteam-based** software that talks to steam, and they differ by who made them and whether the source is open:

| build | runs on |
|---|---|
| **SLSsteam** | linux |
| **HeadCrab** | linux |
| **OpenValve** | windows |
| **HubCapTools** | windows |

they're not competing tools for the best  and not forks of each other — HeadCrab, OpenValve and HubCapTools are each someone's own build *on top of* SLSsteam (and ace knows the devs and the projects too and is fine with all so :p if u have any problem). that's why paws doesn't care which one you use: they all read the same config format, so **adding games, dropping bundles and editing config work identically on every one of them.** what differs is only how each one gets installed, and paws only automates that where there is something real to automate,

one command answers all of it, and it never guesses — if it can't tell, it says it can't tell:

    paws info           os, steam, and whatever is driving it
    paws info --json    the same, machine readable
    paws info --no-net  skip the github lookup so nothing waits on the network

it covers the os (name, family, arch, read-only-ness, package managers), steam (where it is, client version, channel, whether it's running and whether SLS is injected), and which build is present. `paws info` names HeadCrab and SLSsteam separately when both are on the machine, rather than hiding one behind the other.

this is the same detector `paws doctor` and the home screen use, so all three always agree.

## using it (CLI)

    paws                    the menu (add -w / --window to open it in a new terminal window)
    paws --no-update        open it without looking for a newer paws this time
    paws --version          version and license line

**check and fix**

    paws doctor             check steam, sls and versions (--fix fills in missing config keys,
                            --reset-config puts the latest config in place, old one is backed up,
                            --clear-tickets deletes every cached ticket, copies go to the backups)
    paws fix                see whats broken and repair it: bad indentation, wrong values, typos in
                            config.yaml (--dry-run only looks, -y / --yes doesnt ask, or give it ids
                            to fix just those). what it cant fix safely it reports with line numbers
    paws info               os, steam, and whatever is driving it (--no-net skips the github lookup)
    paws backups            list the backups paws made (--restore puts the newest config.yaml back,
                            --restore NAME puts that one back)

**games**

    paws add 480            add a game (several ids at once works too, --name sets the comment)
    paws add --file X       import a .lua / .manifest / .key / .zip
    paws add --list FILE    ids, links or a copied dlc page from a file (or - for stdin)
    paws add --lookup       look names up on the store for ids that have none
    paws add --missing      add every game the config already has keys, manifests or an id for
    paws drop FILE...       add a game from .lua/.manifest/.key files or a .zip/.rar/.7z/tarball
    paws remove 480         take it out again (--list FILE too)
    paws edit               open config.yaml in nvim / nano (paws edit AppIds jumps to that key)

all of those take `--dry-run` to show what would change without changing it.

**tickets**

    paws activate 480       make tickets (both, or --kind encrypted / normal)
    paws tickets            list cached tickets
    paws tickets show 480   both tickets of an app side by side
    paws tickets share 480  one line of text to send someone a game's tickets
    paws tickets take CODE  save the tickets from a code someone sent you (--no-add to skip adding the game)
    paws tickets pack 480   pack both tickets into one paws1e string (unpack puts it back)

**SLSsteam, plugins, paws itself**

    paws sls install        install or update SLSsteam (asks any/arch and release/debug;
                            --variant / --flavour say the same thing for scripts)
    paws sls update         update it       paws sls uninstall   remove it (--purge sets the config aside too)
    paws sls latest         show the newest release
    paws sls install --source private --url LINK --name HeadCrab
                            a private build from a repo link or a .zip/.7z (sources: github, private, forgejo, local)
    paws plugins            new / import / export / enable / disable plugins, `master on|off` for all of them
    paws plugins download   add SLSsteam's download plugin so the public build downloads (--remove sets it aside)
    paws update             get the newest paws (--check just looks)
    paws update --force     update even when git would stop: local changes get stashed, then it resets
                            onto the remote tip. same on any shell, any os (--no-stash discards them instead)

**looks and setup**

    paws settings           show or set: nsfw, random, sound, icons, type (riced / minimal), notifications,
                            terminal, features, launch, update, auto-add, colorblind
    paws art                ascii art gallery (paws art random, paws art --banner NAME sets the home banner)
    paws alias              print a shell function (--install puts paws on your PATH)
    paws desktop            add the icon + app menu entry (--shortcut for the desktop too, --remove undoes it)
    paws launch             which terminal --window would open
    paws notify             send a test desktop notification

`paws --help` and `paws <command> --help` have the rest. most commands take `--json` if u wanna script them.

## tickets (linux, windows soon)

`paws activate <appid>` asks the steam that's **already running** for a type 2 ticket and drops it into SLSsteam's cache itself. no killing steam, no relaunching it, no waiting for it to come back up.

that works because SLSsteam reads `<config>/cache/encryptedTicket_<appid>.yaml` from disk whenever the live request doesn't return one, and hot-reloads that folder — so a ticket paws writes is picked up by the steam you already have open. which also means it works with no SLSsteam injected at all, or none installed.

if steam is not running, or that genuinely can't work, it falls back to starting steam with SLSsteam in same as before.

## staying safe

everything paws adds is written in a journal, so removing a game takes out exactly what went in and nothing else. anything that restarts steam asks first. files a package manager owns are read only for paws. ur files, keys and account never get uploaded anywhere, it only reaches out for updates, downloads and game info u asked for.

## credits

the awesome gang without which this would not exist, so go say hi (and scroll to the end of the file, i have a surprise):

- [AceSLS](https://github.com/AceSLS)
- [niwia](https://github.com/niwia)
- [Deadboy666](https://github.com/Deadboy666)
- [xamionex](https://github.com/xamionex)
- [ke619](https://github.com/ke619)
- [Arata12](https://github.com/Arata12)
- [petar](https://git.petar.cc/petar)
- [ciscosweater](https://github.com/ciscosweater) (enter-the-wired, where paws gets the download plugin)

<p align="center">
  <img src="assets/moan.png" alt="" width="300">
</p>
HOLY AND PAWS HAD AN ORGASM EVEN HERE THE README MOANED!! :3


## the fine print

ownership features touch ur steam account and cache. paws shows the plan and journals every change, but it comes as-is with no warranty. so dont blame me uwu or else....

---

made with <3 and too many late nights. (◕‿◕) and a lot of care, love and guidance....and stealing 😏...lol. 

<p align="center">
  <img src="assets/gun.jpg" alt="" width="270">
</p>
or else ppl get shot :p
