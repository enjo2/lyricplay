(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = {
    homeView: $("home-view"),
    playerView: $("player-view"),
    searchForm: $("search-form"),
    searchInput: $("search-input"),
    searchSubmit: $("search-submit"),
    searchStatus: $("search-status"),
    suggestions: $("suggestions"),
    resultsSection: $("results-section"),
    resultsHeading: $("results-heading"),
    resultsCount: $("results-count"),
    resultsCache: $("results-cache"),
    resultsGrid: $("results-grid"),
    resultsEmpty: $("results-empty"),
    resultsEmptyMessage: $("results-empty-message"),
    recentSection: $("recent-section"),
    recentGrid: $("recent-grid"),
    clearRecent: $("clear-recent"),
    backButton: $("back-button"),
    playerStatus: $("player-status"),
    coverImage: $("cover-image"),
    coverLetter: $("cover-letter"),
    playerEyebrow: $("player-eyebrow"),
    playerTitle: $("player-title"),
    playerArtist: $("player-artist"),
    playerChannel: $("player-channel"),
    seek: $("seek"),
    currentTime: $("current-time"),
    duration: $("duration"),
    rewind: $("rewind"),
    playToggle: $("play-toggle"),
    playIcon: $("play-icon"),
    forward: $("forward"),
    syncEarlier: $("sync-earlier"),
    syncValue: $("sync-value"),
    syncLater: $("sync-later"),
    muteToggle: $("mute-toggle"),
    volume: $("volume"),
    lyricsBadge: $("lyrics-badge"),
    lyricPrevious: $("lyric-previous"),
    lyricCurrent: $("lyric-current"),
    lyricNext: $("lyric-next"),
    lyricsNote: $("lyrics-note"),
    audio: $("audio"),
    toast: $("toast"),
  };

  const RECENT_KEY = "lyricplay.recent.v1";
  const BASE_TITLE = "lyricplay — find the song. feel every word.";
  const state = {
    screen: "home",
    results: [],
    recent: loadRecent(),
    current: null,
    currentResult: null,
    currentLyrics: null,
    synced: [],
    plainLines: [],
    trackDuration: 0,
    duration: 0,
    lyricIndex: null,
    lastCurrentLyric: null,
    syncOffset: 0,
    searching: false,
    preparing: false,
    searchController: null,
    prepareController: null,
    searchSequence: 0,
    seeking: false,
    lastVolume: 1,
    toastTimer: null,
  };

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function formatTime(value) {
    if (!Number.isFinite(value) || value < 0) {
      return "0:00";
    }
    const total = Math.floor(value);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours > 0) {
      return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }

  function errorMessage(error) {
    const message = String((error && error.message) || error || "Something went wrong.");
    return message.split("\n")[0];
  }

  function setRangeProgress(input, ratio) {
    const percent = clamp(Number.isFinite(ratio) ? ratio : 0, 0, 1) * 100;
    input.style.setProperty("--progress", `${percent}%`);
  }

  function setSearchStatus(message, isError) {
    el.searchStatus.textContent = message;
    el.searchStatus.classList.toggle("is-error", Boolean(isError));
  }

  function setSearchBusy(busy) {
    state.searching = busy;
    el.searchSubmit.disabled = busy;
    const label = el.searchSubmit.querySelector("span");
    if (label) {
      label.textContent = busy ? "Searching" : "Search";
    }
  }

  function toast(message) {
    el.toast.textContent = message;
    el.toast.classList.add("is-visible");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      el.toast.classList.remove("is-visible");
    }, 3400);
  }

  async function fetchJson(url, options) {
    const settings = Object.assign({}, options || {});
    settings.headers = Object.assign(
      { Accept: "application/json" },
      (options && options.headers) || {}
    );
    let response;
    try {
      response = await fetch(url, settings);
    } catch (error) {
      if (error.name === "AbortError") {
        throw error;
      }
      throw new Error("Could not reach the local server.");
    }

    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      // The status code still tells the useful part of the story.
    }
    if (!response.ok) {
      const detail = payload && typeof payload.detail === "string"
        ? payload.detail
        : `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return payload;
  }

  function loadRecent() {
    try {
      const parsed = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.slice(0, 6) : [];
    } catch (error) {
      return [];
    }
  }

  function saveRecent() {
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify(state.recent.slice(0, 6)));
    } catch (error) {
      // Private browsing can disable storage; the session still works.
    }
  }

  function addRecent(result) {
    state.recent = [
      result,
      ...state.recent.filter((item) => item.video_id !== result.video_id),
    ].slice(0, 6);
    saveRecent();
    renderRecent();
  }

  function makeThumb(result, index, recent) {
    const thumb = document.createElement("span");
    thumb.className = "result-thumb";

    const imageUrl = result.thumbnail_url
      || (result.video_id ? `https://i.ytimg.com/vi/${result.video_id}/hqdefault.jpg` : "");
    if (imageUrl) {
      const image = document.createElement("img");
      image.src = imageUrl;
      image.alt = "";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => image.remove());
      thumb.append(image);
    }

    const badge = document.createElement("span");
    badge.className = "result-index";
    badge.textContent = recent ? "↻" : String(index + 1).padStart(2, "0");
    thumb.append(badge);
    return thumb;
  }

  function makeResultCard(result, index, recent) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-card";

    const title = String(result.title || result.song || result.raw_title || "Untitled").trim();
    const artist = String(result.artist || "").trim();
    button.setAttribute("aria-label", `Play ${title}${artist ? ` by ${artist}` : ""}`);

    button.append(makeThumb(result, index, Boolean(recent)));

    const body = document.createElement("span");
    body.className = "result-body";

    const kicker = document.createElement("span");
    kicker.className = "result-kicker";
    kicker.textContent = result.channel || "YouTube";
    body.append(kicker);

    const titleNode = document.createElement("span");
    titleNode.className = "result-title";
    titleNode.textContent = title;
    body.append(titleNode);

    const sub = document.createElement("span");
    sub.className = "result-sub";
    sub.textContent = artist || result.raw_title || "Unknown artist";
    body.append(sub);

    const side = document.createElement("span");
    side.className = "result-side";
    const duration = document.createElement("span");
    duration.className = "result-duration";
    duration.textContent = result.duration_label || "";
    side.append(duration);
    const arrow = document.createElement("span");
    arrow.className = "result-arrow";
    arrow.textContent = "↗";
    arrow.setAttribute("aria-hidden", "true");
    side.append(arrow);

    button.append(body, side);
    button.addEventListener("click", () => selectResult(result));
    return button;
  }

  function renderRecent() {
    el.recentGrid.replaceChildren();
    const hasRecent = state.recent.length > 0;
    el.recentSection.hidden = !hasRecent;
    if (!hasRecent) {
      return;
    }
    state.recent.forEach((result, index) => {
      el.recentGrid.append(makeResultCard(result, index, true));
    });
  }

  function renderSkeletons() {
    el.resultsGrid.replaceChildren();
    el.resultsGrid.hidden = false;
    el.resultsGrid.setAttribute("aria-busy", "true");
    el.resultsEmpty.hidden = true;
    el.resultsSection.hidden = false;
    for (let index = 0; index < 6; index += 1) {
      const card = document.createElement("div");
      card.className = "skeleton-card";
      card.setAttribute("aria-hidden", "true");
      const thumb = document.createElement("div");
      thumb.className = "skeleton-thumb";
      const copy = document.createElement("div");
      copy.className = "skeleton-copy";
      for (let line = 0; line < 3; line += 1) {
        const row = document.createElement("div");
        row.className = "skeleton-line";
        copy.append(row);
      }
      card.append(thumb, copy);
      el.resultsGrid.append(card);
    }
  }

  function renderResults(results, cached, tookMs) {
    el.resultsGrid.removeAttribute("aria-busy");
    el.resultsGrid.replaceChildren();
    el.resultsSection.hidden = false;
    el.resultsGrid.hidden = results.length === 0;
    el.resultsEmpty.hidden = results.length !== 0;
    if (!results.length) {
      el.resultsEmptyMessage.textContent = "No signal found. Try another spelling, artist, or lyric.";
      el.resultsCount.textContent = "";
      el.resultsCache.hidden = true;
      setSearchStatus("No results came back for that search.", true);
      return;
    }

    results.forEach((result, index) => {
      el.resultsGrid.append(makeResultCard(result, index, false));
    });
    el.resultsCount.textContent = `${results.length} ${results.length === 1 ? "track" : "tracks"} · ${Math.max(1, tookMs)} ms`;
    el.resultsCache.hidden = !cached;
    setSearchStatus(
      cached
        ? "Loaded from the local search cache. Choose a track to play."
        : `Found ${results.length} ${results.length === 1 ? "track" : "tracks"} in ${Math.max(1, tookMs)} ms. Choose one to play.`,
      false
    );
  }

  function showSearchError(error) {
    const message = errorMessage(error);
    el.resultsGrid.removeAttribute("aria-busy");
    el.resultsGrid.replaceChildren();
    el.resultsGrid.hidden = true;
    el.resultsEmpty.hidden = false;
    el.resultsEmptyMessage.textContent = message;
    el.resultsCount.textContent = "";
    el.resultsCache.hidden = true;
    el.resultsSection.hidden = false;
    setSearchStatus(message, true);
  }

  async function runSearch(rawQuery) {
    const query = String(rawQuery || "").trim();
    if (!query) {
      el.searchInput.focus();
      return;
    }

    if (state.searchController) {
      state.searchController.abort();
    }
    const controller = new AbortController();
    state.searchController = controller;
    const sequence = ++state.searchSequence;
    state.results = [];
    state.query = query;
    el.searchInput.value = query;
    el.resultsHeading.textContent = `Results for “${query}”`;
    el.resultsCount.textContent = "searching…";
    el.resultsCache.hidden = true;
    setSearchBusy(true);
    setSearchStatus("Searching YouTube and checking the local cache…", false);
    renderSkeletons();

    if (window.innerWidth <= 760) {
      window.setTimeout(() => {
        el.resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 60);
    }

    try {
      const data = await fetchJson(
        `/api/v1/search?q=${encodeURIComponent(query)}&limit=8`,
        { signal: controller.signal }
      );
      if (sequence !== state.searchSequence) {
        return;
      }
      state.results = data.results || [];
      renderResults(state.results, Boolean(data.cached), data.took_ms || 0);
      try {
        const url = new URL(window.location.href);
        url.searchParams.set("q", query);
        window.history.replaceState(null, "", url);
      } catch (error) {
        // A history failure should never break the search.
      }
    } catch (error) {
      if (error.name === "AbortError" || sequence !== state.searchSequence) {
        return;
      }
      showSearchError(error);
    } finally {
      if (sequence === state.searchSequence) {
        setSearchBusy(false);
        state.searchController = null;
      }
    }
  }

  function setCover(result) {
    const title = String(result.song || result.raw_title || "Untitled").trim();
    const letter = title.match(/[A-Za-z0-9]/);
    el.coverLetter.textContent = (letter ? letter[0] : "♪").toUpperCase();

    const imageUrl = result.thumbnail_url
      || (result.video_id ? `https://i.ytimg.com/vi/${result.video_id}/hqdefault.jpg` : "");
    if (imageUrl) {
      el.coverImage.hidden = false;
      el.coverImage.src = imageUrl;
    } else {
      el.coverImage.hidden = true;
      el.coverImage.removeAttribute("src");
    }
  }

  function setPlayerMeta(track, preparing) {
    const title = String(track.title || track.song || track.raw_title || "Untitled").trim();
    const artist = String(track.artist || "Unknown artist").trim();
    el.playerEyebrow.textContent = preparing ? "Preparing track" : "Now playing";
    el.playerTitle.textContent = title;
    el.playerArtist.textContent = artist;
    el.playerChannel.textContent = track.channel ? `YouTube · ${track.channel}` : "YouTube";
    setCover(track);
    document.title = `${title} — ${artist} · lyricplay`;
  }

  function setPlayIcon(isPlaying) {
    el.playIcon.textContent = isPlaying ? "❚❚" : "▶";
    el.playToggle.setAttribute("aria-label", isPlaying ? "Pause" : "Play");
  }

  function setPlayerControlsEnabled(enabled) {
    el.playToggle.disabled = !enabled;
    el.rewind.disabled = !enabled;
    el.forward.disabled = !enabled;
    el.seek.disabled = !enabled;
    el.volume.disabled = !enabled;
    el.muteToggle.disabled = !enabled;
    const syncEnabled = enabled && state.synced.length > 0;
    el.syncEarlier.disabled = !syncEnabled;
    el.syncLater.disabled = !syncEnabled;
  }

  function resetAudio() {
    el.audio.pause();
    el.audio.removeAttribute("src");
    el.audio.load();
    el.currentTime.textContent = "0:00";
    el.duration.textContent = "0:00";
    el.seek.value = "0";
    el.seek.max = "0.01";
    setRangeProgress(el.seek, 0);
    setPlayIcon(false);
    setPlayerControlsEnabled(false);
  }

  function showHome() {
    if (state.prepareController) {
      state.prepareController.abort();
      state.prepareController = null;
    }
    state.preparing = false;
    state.seeking = false;
    state.screen = "home";
    el.playerView.hidden = true;
    el.homeView.hidden = false;
    el.playerView.classList.remove("is-playing", "is-preparing");
    resetAudio();
    document.title = BASE_TITLE;
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => {
      if (state.screen === "home" && window.innerWidth > 760) {
        el.searchInput.focus({ preventScroll: true });
      }
    }, 80);
  }

  function setLyricText(node, text) {
    if (node.textContent !== text) {
      node.textContent = text;
    }
  }

  function resolveLyric(position) {
    if (!state.currentLyrics) {
      return {
        index: null,
        current: "",
        previous: "",
        next: "",
        empty: true,
      };
    }
    if (state.currentLyrics.instrumental) {
      return {
        index: -2,
        current: "Instrumental",
        previous: "",
        next: "",
        empty: true,
      };
    }

    if (state.synced.length) {
      const effective = position - state.syncOffset;
      let low = 0;
      let high = state.synced.length - 1;
      let index = -1;
      while (low <= high) {
        const middle = Math.floor((low + high) / 2);
        if (state.synced[middle].time <= effective) {
          index = middle;
          low = middle + 1;
        } else {
          high = middle - 1;
        }
      }
      if (index < 0) {
        return {
          index: -1,
          current: "",
          previous: "",
          next: state.synced[0] ? state.synced[0].text : "",
          empty: true,
        };
      }
      return {
        index,
        current: state.synced[index].text,
        previous: index > 0 ? state.synced[index - 1].text : "",
        next: index + 1 < state.synced.length ? state.synced[index + 1].text : "",
        empty: false,
      };
    }

    if (state.plainLines.length) {
      const duration = state.duration || state.trackDuration || 0;
      const progress = duration > 0 ? clamp(position / duration, 0, 1) : 0;
      const index = Math.min(
        state.plainLines.length - 1,
        Math.round(progress * (state.plainLines.length - 1))
      );
      return {
        index,
        current: state.plainLines[index],
        previous: index > 0 ? state.plainLines[index - 1] : "",
        next: index + 1 < state.plainLines.length ? state.plainLines[index + 1] : "",
        empty: false,
      };
    }

    return {
      index: -3,
      current: "No lyrics found",
      previous: "",
      next: "",
      empty: true,
    };
  }

  function animateCurrentLyric(text) {
    if (state.lastCurrentLyric === text) {
      return;
    }
    state.lastCurrentLyric = text;
    el.lyricCurrent.classList.remove("is-changing");
    // Force a reflow so the animation can restart for a new line.
    void el.lyricCurrent.offsetWidth;
    el.lyricCurrent.classList.add("is-changing");
  }

  function renderLyrics(position, force) {
    const view = resolveLyric(position);
    const currentText = view.current || "· · ·";
    if (force || state.lyricIndex !== view.index) {
      animateCurrentLyric(currentText);
    }
    state.lyricIndex = view.index;

    setLyricText(el.lyricPrevious, view.previous || "");
    setLyricText(el.lyricCurrent, currentText);
    setLyricText(el.lyricNext, view.next || "");
    el.lyricPrevious.hidden = !view.previous;
    el.lyricNext.hidden = !view.next;

    const length = currentText.length;
    el.lyricCurrent.classList.toggle("is-long", length > 32 && length <= 62);
    el.lyricCurrent.classList.toggle("is-longer", length > 62);
    el.lyricCurrent.classList.toggle("is-empty", Boolean(view.empty));
  }

  function updatePlaybackUI() {
    const current = Number.isFinite(el.audio.currentTime) ? el.audio.currentTime : 0;
    if (Number.isFinite(el.audio.duration) && el.audio.duration > 0) {
      state.duration = el.audio.duration;
    } else if (state.trackDuration > 0) {
      state.duration = state.trackDuration;
    } else {
      state.duration = 0;
    }

    if (!state.seeking) {
      el.seek.max = String(Math.max(state.duration, 0.01));
      el.seek.value = String(clamp(current, 0, state.duration || 0));
      setRangeProgress(el.seek, state.duration > 0 ? current / state.duration : 0);
    }
    el.currentTime.textContent = formatTime(current);
    el.duration.textContent = formatTime(state.duration);
  }

  function setLyricsBadge(lyrics) {
    if (!lyrics) {
      el.lyricsBadge.textContent = "NO LYRICS";
      return;
    }
    if (lyrics.instrumental) {
      el.lyricsBadge.textContent = "INSTRUMENTAL";
      return;
    }
    if (lyrics.synced && lyrics.synced.length) {
      el.lyricsBadge.textContent = `${(lyrics.source || "LRCLIB").toUpperCase()} · SYNCED`;
      return;
    }
    if (lyrics.plain) {
      el.lyricsBadge.textContent = `${(lyrics.source || "LRCLIB").toUpperCase()} · PLAIN`;
      return;
    }
    el.lyricsBadge.textContent = "NO LYRICS";
  }

  function setLyricsNote(lyrics) {
    if (!lyrics) {
      setLyricsNoteText("No lyrics found for this track.");
      return;
    }
    if (lyrics.instrumental) {
      setLyricsNoteText("This track is instrumental.");
      return;
    }
    if (lyrics.synced && lyrics.synced.length) {
      setLyricsNoteText("Synced from LRC timestamps. Use [ and ] to nudge.");
      return;
    }
    if (lyrics.plain) {
      setLyricsNoteText("No timestamps — lines are paced across the track.");
      return;
    }
    setLyricsNoteText("No lyrics found for this track.");
  }

  function setLyricsNoteText(message) {
    el.lyricsNote.textContent = message;
  }

  function updateSyncLabel() {
    const value = state.syncOffset;
    el.syncValue.textContent = value === 0
      ? "0.0s"
      : `${value > 0 ? "+" : ""}${value.toFixed(1)}s`;
  }

  function adjustSync(delta) {
    state.syncOffset = Math.round(clamp(state.syncOffset + delta, -10, 10) * 10) / 10;
    updateSyncLabel();
    renderLyrics(el.audio.currentTime || 0, true);
  }

  function applyPreparedTrack(data, original) {
    state.current = data;
    state.currentResult = original;
    state.currentLyrics = data.lyrics || null;
    state.synced = (data.lyrics && Array.isArray(data.lyrics.synced))
      ? data.lyrics.synced.slice().sort((left, right) => left.time - right.time)
      : [];
    state.plainLines = (data.lyrics && data.lyrics.plain)
      ? data.lyrics.plain.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
      : [];
    state.trackDuration = Number(data.track.duration) || 0;
    state.duration = state.trackDuration;
    state.lyricIndex = null;
    state.lastCurrentLyric = null;
    state.syncOffset = 0;
    updateSyncLabel();

    setPlayerMeta(data.track, false);
    setLyricsBadge(data.lyrics);
    setLyricsNote(data.lyrics);

    el.playerView.classList.remove("is-preparing");
    el.playerStatus.textContent = data.took_ms > 900
      ? `ready · ${(data.took_ms / 1000).toFixed(1)}s`
      : "ready";
    setPlayerControlsEnabled(true);

    el.audio.src = data.audio_url;
    el.audio.load();
    updateVolumeUI();
    el.duration.textContent = formatTime(state.trackDuration);
    renderLyrics(0, true);

    const merged = Object.assign({}, original, data.track, {
      thumbnail_url: data.track.thumbnail_url || original.thumbnail_url,
    });
    addRecent(merged);

    const playAttempt = el.audio.play();
    if (playAttempt && typeof playAttempt.catch === "function") {
      playAttempt.catch(() => {
        setPlayIcon(false);
        toast("Track ready — press play when you are.");
      });
    }
  }

  async function selectResult(result) {
    if (state.preparing) {
      toast("Still preparing the current track. Press back to cancel.");
      return;
    }

    state.preparing = true;
    state.screen = "player";
    state.current = null;
    state.currentResult = result;
    state.currentLyrics = null;
    state.synced = [];
    state.plainLines = [];
    state.trackDuration = Number(result.duration) || 0;
    state.duration = state.trackDuration;
    state.lyricIndex = null;
    state.lastCurrentLyric = null;
    state.syncOffset = 0;
    state.seeking = false;
    updateSyncLabel();

    el.homeView.hidden = true;
    el.playerView.hidden = false;
    el.playerView.classList.add("is-preparing");
    el.playerView.classList.remove("is-playing");
    el.playerStatus.textContent = "preparing";
    el.lyricsBadge.textContent = "FETCHING";
    el.lyricsBadge.hidden = false;
    setLyricsNoteText("Downloading audio and matching lyrics.");
    el.lyricPrevious.hidden = true;
    el.lyricNext.hidden = true;
    setLyricText(el.lyricCurrent, "Tuning the signal…");
    el.lyricCurrent.className = "lyric-current";
    el.duration.textContent = formatTime(state.trackDuration);
    setPlayerMeta(result, true);
    resetAudio();
    setPlayerControlsEnabled(false);
    el.playerTitle.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "smooth" });

    const controller = new AbortController();
    state.prepareController = controller;
    try {
      const payload = {
        video_id: result.video_id,
        raw_title: result.raw_title || "",
        channel: result.channel || "",
        artist: result.artist || "",
        song: result.song || result.title || result.raw_title || "Untitled",
        duration: Number.isFinite(Number(result.duration)) ? Number(result.duration) : null,
        web_url: result.web_url || "",
      };
      const data = await fetchJson("/api/v1/tracks/prepare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (state.screen !== "player" || state.prepareController !== controller) {
        return;
      }
      applyPreparedTrack(data, result);
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      if (state.screen !== "player") {
        return;
      }
      el.playerView.classList.remove("is-preparing");
      el.playerStatus.textContent = "error";
      el.lyricsBadge.textContent = "ERROR";
      setLyricsNoteText("The track could not be prepared.");
      setLyricText(el.lyricCurrent, "Could not load this track");
      el.lyricCurrent.className = "lyric-current is-empty";
      el.lyricPrevious.hidden = true;
      el.lyricNext.hidden = true;
      toast(errorMessage(error));
    } finally {
      if (state.prepareController === controller) {
        state.prepareController = null;
        state.preparing = false;
      }
    }
  }

  function togglePlay() {
    if (!el.audio.src) {
      return;
    }
    if (el.audio.paused) {
      const attempt = el.audio.play();
      if (attempt && typeof attempt.catch === "function") {
        attempt.catch(() => toast("Playback could not start."));
      }
    } else {
      el.audio.pause();
    }
  }

  function seekBy(seconds) {
    if (!el.audio.src) {
      return;
    }
    const duration = Number.isFinite(el.audio.duration) && el.audio.duration > 0
      ? el.audio.duration
      : state.duration;
    const next = clamp((el.audio.currentTime || 0) + seconds, 0, duration || 0);
    el.audio.currentTime = next;
    updatePlaybackUI();
    renderLyrics(next, true);
  }

  function updateVolumeUI() {
    const value = el.audio.volume;
    el.volume.value = String(value);
    setRangeProgress(el.volume, value);
    const muted = value === 0;
    el.muteToggle.textContent = muted ? "◌" : "◖";
    el.muteToggle.setAttribute("aria-label", muted ? "Unmute" : "Mute");
  }

  function setVolume(value) {
    const next = clamp(value, 0, 1);
    if (next > 0) {
      state.lastVolume = next;
    }
    el.audio.volume = next;
    updateVolumeUI();
  }

  function toggleMute() {
    if (el.audio.volume > 0) {
      setVolume(0);
    } else {
      setVolume(state.lastVolume || 1);
    }
  }

  function bindEvents() {
    el.searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      runSearch(el.searchInput.value);
    });

    el.suggestions.addEventListener("click", (event) => {
      const button = event.target.closest(".chip");
      if (!button) {
        return;
      }
      const query = button.getAttribute("data-query") || button.textContent || "";
      el.searchInput.value = query;
      runSearch(query);
    });

    el.clearRecent.addEventListener("click", () => {
      state.recent = [];
      saveRecent();
      renderRecent();
      toast("Listening history cleared.");
    });

    el.backButton.addEventListener("click", showHome);

    const brand = document.querySelector(".brand");
    if (brand) {
      brand.addEventListener("click", (event) => {
        event.preventDefault();
        showHome();
      });
    }

    el.playToggle.addEventListener("click", togglePlay);
    el.rewind.addEventListener("click", () => seekBy(-5));
    el.forward.addEventListener("click", () => seekBy(5));

    el.seek.addEventListener("pointerdown", () => {
      state.seeking = true;
    });
    el.seek.addEventListener("input", () => {
      state.seeking = true;
      const value = Number(el.seek.value) || 0;
      el.currentTime.textContent = formatTime(value);
      setRangeProgress(el.seek, state.duration > 0 ? value / state.duration : 0);
      if (Number.isFinite(el.audio.duration) && el.audio.duration > 0) {
        el.audio.currentTime = clamp(value, 0, el.audio.duration);
      }
      renderLyrics(value, true);
    });
    el.seek.addEventListener("change", () => {
      state.seeking = false;
    });
    el.seek.addEventListener("pointerup", () => {
      state.seeking = false;
    });

    el.volume.addEventListener("input", () => {
      setVolume(Number(el.volume.value) || 0);
    });
    el.muteToggle.addEventListener("click", toggleMute);
    el.syncEarlier.addEventListener("click", () => adjustSync(-0.1));
    el.syncLater.addEventListener("click", () => adjustSync(0.1));

    el.audio.addEventListener("play", () => {
      el.playerView.classList.add("is-playing");
      setPlayIcon(true);
      el.playerStatus.textContent = "playing";
    });
    el.audio.addEventListener("pause", () => {
      el.playerView.classList.remove("is-playing");
      setPlayIcon(false);
      if (state.screen === "player" && !state.preparing && el.audio.src) {
        el.playerStatus.textContent = "paused";
      }
    });
    el.audio.addEventListener("ended", () => {
      el.playerView.classList.remove("is-playing");
      setPlayIcon(false);
      el.playerStatus.textContent = "finished";
    });
    el.audio.addEventListener("loadedmetadata", () => {
      if (Number.isFinite(el.audio.duration) && el.audio.duration > 0) {
        state.duration = el.audio.duration;
        el.duration.textContent = formatTime(state.duration);
        el.seek.max = String(state.duration);
      }
    });
    el.audio.addEventListener("volumechange", updateVolumeUI);
    el.audio.addEventListener("error", () => {
      if (!el.audio.src) {
        return;
      }
      toast("The audio stream could not be loaded. Try another result.");
    });
    el.coverImage.addEventListener("error", () => {
      el.coverImage.hidden = true;
    });
    el.coverImage.addEventListener("load", () => {
      el.coverImage.hidden = false;
    });

    document.addEventListener("keydown", (event) => {
      const target = event.target;
      const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
      const typing = tag === "input" || tag === "textarea" || tag === "select"
        || (target && target.isContentEditable);
      const interactive = typing || tag === "button" || tag === "a";

      if (event.key === "/" && !typing && state.screen === "home") {
        event.preventDefault();
        el.searchInput.focus();
        return;
      }

      if (event.key === "Escape") {
        if (state.screen === "player") {
          showHome();
        } else if (typing) {
          target.blur();
        }
        return;
      }

      if (state.screen !== "player" || interactive) {
        return;
      }

      if (event.code === "Space") {
        event.preventDefault();
        togglePlay();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        seekBy(-5);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        seekBy(5);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setVolume(el.audio.volume + 0.05);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setVolume(el.audio.volume - 0.05);
      } else if (event.key === "[") {
        adjustSync(-0.1);
      } else if (event.key === "]") {
        adjustSync(0.1);
      } else if (event.key.toLowerCase() === "m") {
        toggleMute();
      }
    });
  }

  function startTicker() {
    function tick() {
      if (state.screen === "player" && !el.playerView.hidden) {
        updatePlaybackUI();
        renderLyrics(Number.isFinite(el.audio.currentTime) ? el.audio.currentTime : 0, false);
      }
      window.requestAnimationFrame(tick);
    }
    window.requestAnimationFrame(tick);
  }

  function init() {
    document.title = BASE_TITLE;
    updateSyncLabel();
    updateVolumeUI();
    renderRecent();
    bindEvents();
    startTicker();

    const initialQuery = new URLSearchParams(window.location.search).get("q");
    if (initialQuery) {
      el.searchInput.value = initialQuery;
      runSearch(initialQuery);
    } else if (window.matchMedia("(pointer: fine)").matches) {
      el.searchInput.focus({ preventScroll: true });
    }
  }

  init();
})();
