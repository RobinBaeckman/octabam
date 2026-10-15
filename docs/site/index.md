# octabam manual

<div class="manual-intro" markdown="1">

<p class="manual-eyebrow">COMMUNITY FIRMWARE · OS 1.40C</p>

<p class="manual-lead">Your Octatrack, remixed.</p>

New ways to sequence, shape sound, and play. octabam combines community
modules into a firmware image you build from your own copy of Octatrack
OS 1.40C. Each module is credited to its author.

[Choose a remix](choosing.md){ .manual-button }
[Build and flash →](build-flash.md){ .manual-text-link }

Unofficial community software. Read [Safety and recovery](safety.md)
before flashing.

</div>

## Three ways to play

The same core features, three approaches to effects. Compare the
[full remix details](choosing.md), or explore a remix below.

<div class="remix-grid" markdown="1">

<div class="remix-card" markdown="1">

<p class="manual-eyebrow">01 / CORE</p>

### Keep the stock effects

The core modules, all 14 stock effects, and both menus unchanged, with
LO-FI's AMF knob fixed.

[Explore octabam-core →](remix-core.md)

</div>

<div class="remix-card" markdown="1">

<p class="manual-eyebrow">02 / INSERTS</p>

### Shape every track

SPECTRUM, CHARACTER, MODULATION, TRANSIENT and EUCLID on FX1 and FX2,
GATE VERB, and the stock DELAY.

[Explore octabam-inserts →](remix-inserts.md)

</div>

<div class="remix-card" markdown="1">

<p class="manual-eyebrow">03 / BUS</p>

### Play the sends

DELAY on track 1, REVERB on track 5, and SEND on the other tracks except
track 8, which keeps stock DELAY. Three inserts on FX1.

[Explore octabam-bus →](remix-bus.md)

</div>

</div>

!!! note "Current status: verified under the port"
    None of the three remixes has run on a unit. Each is verified under the
    port: an emulator build boots the image and every gate passes, but the
    emulator is not the hardware. The closest hardware run is bottleservice
    — the same delay and reverb bus without the core modules — which ran on
    Sam's MKII (images A0–A6, recorded in the changelog).

## Before you flash

!!! warning "This is not official Elektron firmware"
    octabam is community software and is not supported by Elektron. A failed
    flash can leave the installed OS unable to boot until stock OS is
    reinstalled. Recovery requires a working Startup Menu, a DIN MIDI
    interface, and a copy of the stock OS. Keep these available before
    flashing. See
    [Safety and recovery](safety.md) before flashing.

    **Do not share a built image.** A built `.bin` or `.syx` contains
    Elektron's OS.

## Make it yours

- [Build your own remix](own-remix.md) — combine existing modules, check
  compatibility, and build a custom selection.
- [BRAIN](brain.md) — the on-unit screens: templates, settings, defaults, and
  switching remixes from the card.
- [Modules reference](reference/modules.md) — every module, its author, and
  its proof status.

## How it works

**Modules** are individual contributions; **remixes** are named selections
built into one firmware image. The build places the code, wires the hooks by
symbol, refuses collisions by name, and proves every ported module against
its author's own build, byte for byte. No firmware is distributed here:
a built image contains Elektron's OS, so you build it yourself, on your
machine. octabam is unofficial community software, not affiliated with
Elektron.

[Explore the repository on GitHub →](https://github.com/sambanks/octabam)
