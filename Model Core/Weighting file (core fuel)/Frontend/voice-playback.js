(function exposeVoicePlayback(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.MolingVoicePlayback = api;
  }
})(typeof window === "undefined" ? globalThis : window, () => {
  const LOCAL_VOICE_PREFIX = "voice:";

  function resolveSynthesisVoice(preference, voices) {
    if (
      typeof preference !== "string" ||
      !preference.startsWith(LOCAL_VOICE_PREFIX)
    ) {
      return { voice: undefined, unavailable: false };
    }
    const voiceName = preference.slice(LOCAL_VOICE_PREFIX.length);
    const available = Array.isArray(voices)
      ? voices.some((voice) => voice?.name === voiceName)
      : false;
    return available
      ? { voice: voiceName, unavailable: false }
      : { voice: undefined, unavailable: true };
  }

  return Object.freeze({ resolveSynthesisVoice });
});
