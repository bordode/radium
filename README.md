# Radium

Hobby OS.

## Memory Map

| Begin       | End (incl.) | Purpose
| ----------- | ----------- | -------
| `0000_0000` | `0000_0fff` | Null page. Not mapped in.
| `0000_1000` | `000f_ffff` | Low memory. Untouched.
| `0010_0000` | *???*       | The kernel is loaded here by GRUB.
| *???*       | `0fbf_ffff` | Kernel dynamic allocation area.
| `0fc0_0000` | `0fc0_0fff` | Kernel stack guard page. Not mapped in.
| `0fc0_1000` | `0fff_ffff` | Kernel stack.
| `1000_0000` | `ffbf_ffff` | User address space.
| `ffc0_0000` | `ffff_efff` | Recursively mapped page tables
| `ffff_f000` | `ffff_ffff` | Recursively mapped page directory

## Cloud9 Assembly investigation helper

The repository includes a dependency-free Python helper for organizing
astronomy article excerpts into claims, risk labels, and follow-up checks:

```sh
python3 tools/cloud9_assembly.py
python3 tools/cloud9_assembly.py article.txt -o investigation.md
```

Run it with no input to emit built-in investigation seeds for the two Avi Loeb
essays about Sagittarius A* gas clouds and first-star enrichment. To avoid
checking copyrighted article text into the repository, pass local notes or
excerpts through files or standard input when deeper triage is needed.
