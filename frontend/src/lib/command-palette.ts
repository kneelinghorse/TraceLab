/** Shared entry point for the shell toolbar, Home and keyboard shortcut. */
export const OPEN_COMMAND_PALETTE_EVENT = "tracelab:open-command-palette";

export function openCommandPalette() {
  window.dispatchEvent(new Event(OPEN_COMMAND_PALETTE_EVENT));
}
