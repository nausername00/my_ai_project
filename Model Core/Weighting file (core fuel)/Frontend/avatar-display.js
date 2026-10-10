(function exposeAvatarDisplay(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.MolingAvatarDisplay = api;
  }
})(typeof window === "undefined" ? globalThis : window, () => {
  const MODES = Object.freeze({
    FOLLOW: "follow",
    BASE: "base",
  });

  function normalizeMode(mode) {
    return mode === MODES.BASE ? MODES.BASE : MODES.FOLLOW;
  }

  function getAvatarCandidates({
    baseAvatar,
    emotionAvatars = {},
    mood,
    mode = MODES.FOLLOW,
  }) {
    const candidates =
      normalizeMode(mode) === MODES.FOLLOW
        ? [emotionAvatars?.[mood], baseAvatar]
        : [baseAvatar];
    return [
      ...new Set(
        candidates.filter(
          (candidate) => typeof candidate === "string" && candidate,
        ),
      ),
    ];
  }

  return Object.freeze({ MODES, normalizeMode, getAvatarCandidates });
});
