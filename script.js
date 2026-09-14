/* Shagai pod hity landing. Vanilla JS, no dependencies. ASCII only.
   Tilda-safe: the page may be cut into many blocks, each with its own
   <div class="hits"> wrapper. Every module searches the whole document,
   the script initialises once per page (flag on window) and works whether
   it is included before, between or after the markup, even twice. */
(function () {
  'use strict';

  if (window.__hitsLandingInit) return;
  window.__hitsLandingInit = true;

  var motionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  function prefersReduced() { return !!(motionQuery && motionQuery.matches); }
  function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function closest(node, selector) {
    while (node && node.nodeType === 1) {
      if (node.matches && node.matches(selector)) return node;
      node = node.parentNode;
    }
    return null;
  }
  function toArray(list) { return Array.prototype.slice.call(list || []); }
  function all(selector) { return toArray(document.querySelectorAll(selector)); }
  function trim(value) { return String(value == null ? '' : value).replace(/^\s+|\s+$/g, ''); }
  function playSafe(media) {
    var promise = media.play();
    if (promise && typeof promise.catch === 'function') promise.catch(function () { /* blocked */ });
  }

  /* ---------------------------------------------------------
     1. Smooth anchor scroll (own rAF animation)
     --------------------------------------------------------- */
  function initAnchors() {
    var pageRaf = 0;
    function stopPageScroll() { if (pageRaf) { cancelAnimationFrame(pageRaf); pageRaf = 0; } }

    function scrollPageTo(targetY) {
      var doc = document.documentElement;
      var startY = window.pageYOffset || doc.scrollTop || 0;
      var maxY = Math.max(0, doc.scrollHeight - window.innerHeight);
      var endY = Math.max(0, Math.min(targetY, maxY));
      var dist = endY - startY;
      stopPageScroll();
      if (prefersReduced() || Math.abs(dist) < 2) { window.scrollTo(0, endY); return; }
      var duration = Math.min(1100, Math.max(350, Math.abs(dist) * 0.45));
      var startTime = null;
      function step(now) {
        if (startTime === null) startTime = now;
        var p = Math.min(1, (now - startTime) / duration);
        window.scrollTo(0, startY + dist * ease(p));
        pageRaf = p < 1 ? requestAnimationFrame(step) : 0;
      }
      pageRaf = requestAnimationFrame(step);
    }

    window.addEventListener('wheel', stopPageScroll, { passive: true });
    window.addEventListener('touchstart', stopPageScroll, { passive: true });
    window.addEventListener('keydown', stopPageScroll);

    document.addEventListener('click', function (e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var link = closest(e.target, 'a[href]');
      if (!link || !closest(link, '.hits')) return;
      var href = link.getAttribute('href') || '';
      if (href.charAt(0) !== '#' || href.length < 2) return;

      /* tariff buttons without payment links yet: no jump */
      if (link.hasAttribute('data-tariff')) { e.preventDefault(); return; }

      var target = document.getElementById(href.slice(1));
      if (!target) return;
      e.preventDefault();
      var top = target.getBoundingClientRect().top + (window.pageYOffset || document.documentElement.scrollTop || 0);
      scrollPageTo(top);
      if (window.history && typeof window.history.replaceState === 'function') {
        try { window.history.replaceState(null, '', href); } catch (err) { /* ignore */ }
      }
    });
  }

  /* ---------------------------------------------------------
     2. Tariffs carousel (mobile): snap + dots + rAF animation
     --------------------------------------------------------- */
  function initCarousel(box) {
    if (box.__hitsCarousel) return;
    box.__hitsCarousel = true;
    var track = box.querySelector('[data-carousel-track]');
    if (!track) return;
    var slides = toArray(track.querySelectorAll('[data-slide]'));
    var dotsBox = box.querySelector('[data-carousel-dots]');
    var dots = dotsBox ? toArray(dotsBox.querySelectorAll('[data-dot]')) : [];
    if (!slides.length) return;

    var current = -1;
    var raf = 0;
    var locked = false;
    var ticking = false;

    function padLeft() { return parseFloat(window.getComputedStyle(track).paddingLeft) || 0; }
    function maxScroll() { return Math.max(0, track.scrollWidth - track.clientWidth); }

    function setActive(index) {
      if (index === current) return;
      current = index;
      slides.forEach(function (slide, k) { slide.classList.toggle('is-current', k === index); });
      dots.forEach(function (dot, k) {
        dot.classList.toggle('is-active', k === index);
        dot.setAttribute('aria-current', k === index ? 'true' : 'false');
      });
    }

    function targetFor(index) {
      var trackBox = track.getBoundingClientRect();
      var slideBox = slides[index].getBoundingClientRect();
      var x = track.scrollLeft + (slideBox.left - trackBox.left) - padLeft();
      return Math.max(0, Math.min(x, maxScroll()));
    }

    function nearestIndex() {
      if (track.scrollLeft >= maxScroll() - 2 && maxScroll() > 0) return slides.length - 1;
      var anchor = track.getBoundingClientRect().left + padLeft();
      var best = 0;
      var bestDist = Infinity;
      slides.forEach(function (slide, k) {
        var d = Math.abs(slide.getBoundingClientRect().left - anchor);
        if (d < bestDist) { bestDist = d; best = k; }
      });
      return best;
    }

    function restoreSnap() {
      track.classList.remove('is-animating');
      track.style.scrollSnapType = '';
      locked = false;
    }

    function cancelAnimation() {
      if (!raf) return;
      cancelAnimationFrame(raf);
      raf = 0;
      restoreSnap();
    }

    function animateTo(index) {
      index = Math.max(0, Math.min(index, slides.length - 1));
      var from = track.scrollLeft;
      var to = targetFor(index);
      var dist = to - from;
      cancelAnimation();
      setActive(index);
      if (Math.abs(dist) < 2) return;

      /* snap fights programmatic scrolling: switch it off while animating */
      locked = true;
      track.classList.add('is-animating');
      track.style.scrollSnapType = 'none';

      if (prefersReduced()) {
        track.scrollLeft = to;
        requestAnimationFrame(restoreSnap);
        return;
      }

      var duration = Math.min(650, Math.max(280, Math.abs(dist) * 0.6));
      var startTime = null;
      function step(now) {
        if (startTime === null) startTime = now;
        var p = Math.min(1, (now - startTime) / duration);
        track.scrollLeft = from + dist * ease(p);
        if (p < 1) {
          raf = requestAnimationFrame(step);
        } else {
          raf = 0;
          track.scrollLeft = to;
          requestAnimationFrame(function () {
            restoreSnap();
            setActive(nearestIndex());
          });
        }
      }
      raf = requestAnimationFrame(step);
    }

    track.addEventListener('scroll', function () {
      if (locked || ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        ticking = false;
        setActive(nearestIndex());
      });
    }, { passive: true });

    track.addEventListener('touchstart', cancelAnimation, { passive: true });
    track.addEventListener('wheel', cancelAnimation, { passive: true });

    dots.forEach(function (dot, k) {
      dot.addEventListener('click', function () { animateTo(k); });
    });

    window.addEventListener('resize', function () {
      if (locked) return;
      setActive(nearestIndex());
    });

    setActive(0);
  }

  /* ---------------------------------------------------------
     3. Media slots. Only links go into the markup:
        data-video on [data-track] rows and .hits-player (Kinescope or .mp4/.webm),
        data-audio on hero rows (.mp3/.m4a), data-photo on trainer photo zones.
     --------------------------------------------------------- */
  var KINESCOPE_ALLOW = 'autoplay; fullscreen; picture-in-picture; encrypted-media';
  var music = null;   /* shared <audio> */
  var player = null;  /* { pause: fn } */

  function parseVideo(raw) {
    var value = trim(raw);
    if (!value) return null;
    var match = /^(?:https?:)?\/\/(?:www\.)?kinescope\.io\/(?:embed\/|watch\/|video\/)?([A-Za-z0-9_-]{6,})/i.exec(value);
    if (!match && /^[A-Za-z0-9_-]{20,}$/.test(value)) match = [value, value];
    if (match) return { kind: 'kinescope', src: 'https://kinescope.io/embed/' + match[1] + '?autoplay=1' };
    if (/[\/.]/.test(value)) return { kind: 'file', src: value };
    return null;
  }

  function pauseMusic() { if (music && !music.paused) music.pause(); }

  function initPlayer() {
    var box = document.querySelector('.hits-player');
    var rows = all('[data-track]');
    if (!box && !rows.length) return;
    var picture = box ? (box.querySelector('picture') || box.querySelector('img')) : null;
    var image = box ? box.querySelector('img') : null;

    function activeRow() {
      for (var k = 0; k < rows.length; k++) if (rows[k].classList.contains('is-active')) return rows[k];
      return rows[0] || null;
    }
    function rowVideo(row) { return row ? parseVideo(row.getAttribute('data-video')) : null; }
    function boxVideo() { return rowVideo(activeRow()) || (box ? parseVideo(box.getAttribute('data-video')) : null); }
    function currentMedia() { return box ? box.querySelector('.hits-player__media') : null; }

    function clearMedia() {
      if (!box) return;
      var media = currentMedia();
      if (media) {
        if (media.tagName === 'VIDEO') {
          try { media.pause(); media.removeAttribute('src'); media.load(); } catch (err) { /* ignore */ }
        }
        media.parentNode.removeChild(media);
      }
      if (picture) picture.hidden = false;
      box.classList.remove('is-playing');
    }

    function showMedia(info) {
      if (!box || !info) return;
      clearMedia();
      var el;
      if (info.kind === 'kinescope') {
        el = document.createElement('iframe');
        el.setAttribute('allow', KINESCOPE_ALLOW);
        el.setAttribute('allowfullscreen', '');
        el.setAttribute('frameborder', '0');
        if (image && image.alt) el.setAttribute('title', image.alt);
        el.setAttribute('src', info.src);
      } else {
        el = document.createElement('video');
        el.setAttribute('controls', '');
        el.setAttribute('playsinline', '');
        el.setAttribute('autoplay', '');
        el.setAttribute('preload', 'auto');
        el.playsInline = true;
        if (image && image.currentSrc) el.setAttribute('poster', image.currentSrc);
        if (image && image.alt) el.setAttribute('aria-label', image.alt);
        el.setAttribute('src', info.src);
      }
      el.className = 'hits-player__media';
      if (picture) picture.hidden = true;
      box.appendChild(el);
      box.classList.add('is-playing');
      pauseMusic();
      if (el.tagName === 'VIDEO') playSafe(el);
    }

    function setActive(row) {
      rows.forEach(function (other) {
        var on = other === row;
        other.classList.toggle('is-active', on);
        var button = other.querySelector('.hits-play');
        if (button) button.classList.toggle('hits-play--active', on);
      });
      if (box) box.classList.toggle('is-ready', !!boxVideo());
    }

    rows.forEach(function (row) {
      row.addEventListener('click', function () {
        var media = currentMedia();
        if (row.classList.contains('is-active') && media) {
          if (media.tagName === 'VIDEO') { if (media.paused) playSafe(media); else media.pause(); }
          return;
        }
        setActive(row);
        var info = rowVideo(row);
        if (info) showMedia(info); else clearMedia();
      });
    });

    if (box) {
      box.addEventListener('click', function () {
        if (currentMedia()) return;
        var info = boxVideo();
        if (info) showMedia(info);
      });
      box.classList.toggle('is-ready', !!boxVideo());
    }

    player = {
      pause: function () {
        var media = currentMedia();
        if (!media) return;
        /* a cross-origin iframe cannot be paused: put the picture back */
        if (media.tagName === 'VIDEO') media.pause(); else clearMedia();
      }
    };
  }

  function initMusic() {
    var rows = all('[data-audio]').filter(function (row) { return !!trim(row.getAttribute('data-audio')); });
    if (!rows.length) return;
    music = document.querySelector('audio.hits-audio');
    if (!music) {
      music = document.createElement('audio');
      music.className = 'hits-audio';
      music.setAttribute('preload', 'none');
      (document.body || document.documentElement).appendChild(music);
    }
    var musicRow = null;

    function render() {
      var playing = !music.paused && !music.ended;
      rows.forEach(function (row) {
        var on = playing && row === musicRow;
        row.classList.toggle('is-playing', on);
        var button = row.querySelector('.hits-play');
        if (!button) return;
        button.classList.toggle('hits-play--active', on);
        var use = button.querySelector('use');
        if (use) use.setAttribute('href', on ? '#i-pause' : '#i-play');
        var label = button.getAttribute(on ? 'data-label-pause' : 'data-label-play');
        if (label) button.setAttribute('aria-label', label);
      });
    }

    rows.forEach(function (row) {
      var button = row.querySelector('.hits-play');
      if (!button) return;
      if (button.tagName === 'A') button.setAttribute('role', 'button');
      button.addEventListener('click', function (e) {
        e.preventDefault();
        var src = trim(row.getAttribute('data-audio'));
        if (musicRow !== row || music.getAttribute('src') !== src) {
          musicRow = row;
          music.setAttribute('src', src);
          playSafe(music);
        } else if (music.paused) {
          playSafe(music);
        } else {
          music.pause();
        }
        render();
      });
    });

    ['play', 'playing', 'pause', 'ended', 'emptied', 'error'].forEach(function (type) {
      music.addEventListener(type, render);
    });
    render();
  }

  function initPhotos() {
    all('[data-photo]').forEach(function (zone) {
      var src = trim(zone.getAttribute('data-photo'));
      if (!src) return;
      for (var k = 0; k < zone.children.length; k++) {
        var tag = zone.children[k].tagName;
        if (tag === 'IMG' || tag === 'PICTURE') return;
      }
      var card = closest(zone, '.hits-trainer');
      var name = card ? card.querySelector('.hits-trainer__name') : null;
      var img = document.createElement('img');
      img.setAttribute('loading', 'lazy');
      img.setAttribute('decoding', 'async');
      img.setAttribute('alt', name ? trim(name.textContent) : '');
      img.setAttribute('src', src);
      zone.insertBefore(img, zone.firstChild);
      zone.classList.add('has-photo');
    });
  }

  function initMediaExclusion() {
    /* only one thing plays at a time: music pauses the video and vice versa */
    document.addEventListener('play', function (e) {
      var target = e.target;
      if (!target || target.nodeType !== 1) return;
      if (target === music) { if (player) player.pause(); }
      else if (closest(target, '.hits-player')) pauseMusic();
    }, true);
  }

  /* ---------------------------------------------------------
     4. UTM passthrough to walk-walk.ru and getcourse.ru links
        (any subdomain; relative links go to walk-walk.ru as well)
     --------------------------------------------------------- */
  var UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'erid'];
  var UTM_HOSTS = ['walk-walk.ru', 'getcourse.ru'];

  /* decodes only valid %XX runs and keeps the rest as typed, so raw ad
     macros like vk:%userid% survive instead of throwing URIError */
  function softDecode(raw) {
    return String(raw).replace(/\+/g, ' ').replace(/(?:%[0-9a-f]{2})+/gi, function (run) {
      try { return decodeURIComponent(run); } catch (err) { /* broken UTF-8: piece by piece */ }
      var out = '';
      var at = 0;
      while (at < run.length) {
        var size = Math.min(12, run.length - at);
        for (; size > 0; size -= 3) {
          try { out += decodeURIComponent(run.slice(at, at + size)); break; } catch (err) { /* shorter */ }
        }
        if (size <= 0) { out += run.slice(at, at + 3); size = 3; }
        at += size;
      }
      return out;
    });
  }

  function readUtm() {
    var found = [];
    var query = window.location.search.replace(/^\?/, '');
    if (!query) return found;
    var map = {};
    query.split('&').forEach(function (pair) {
      if (!pair) return;
      var eq = pair.indexOf('=');
      var key = softDecode(eq >= 0 ? pair.slice(0, eq) : pair);
      var value = softDecode(eq >= 0 ? pair.slice(eq + 1) : '');
      if (value && !(key in map)) map[key] = value;
    });
    UTM_KEYS.forEach(function (key) {
      if (map[key]) found.push([key, map[key]]);
    });
    return found;
  }

  function initUtm() {
    var utm = readUtm();
    if (!utm.length) return;

    function isUtmHost(authority) {
      var host = authority.replace(/^.*@/, '').replace(/:\d*$/, '').replace(/\.$/, '').toLowerCase();
      for (var k = 0; k < UTM_HOSTS.length; k++) {
        var root = UTM_HOSTS[k];
        if (host === root || host.slice(-root.length - 1) === '.' + root) return true;
      }
      return false;
    }

    /* absolute and //host links: by host. Relative links (/path, path, ?query)
       stay on walk-walk.ru. Anchors and other schemes (mailto:, tel:,
       javascript:) are left alone. Browsers read a backslash as a slash. */
    function acceptsUtm(href) {
      var url = href.replace(/[\t\n\r]/g, '').replace(/^[\x00- ]+/, '');
      if (!url || url.charAt(0) === '#') return false;
      var match = /^(?:https?:)?[\/\\]{2}([^\/\\?#]*)/i.exec(url);
      if (match) return isUtmHost(match[1]);
      return !/^[a-z][a-z0-9+.\-]*:/i.test(url);
    }

    function decorateLink(link) {
      if (!link || link.nodeType !== 1 || link.tagName !== 'A') return;
      var href = trim(link.getAttribute('href'));
      if (!acceptsUtm(href) || /[?&]utm_/i.test(href)) return;
      var hashAt = href.indexOf('#');
      var hash = hashAt >= 0 ? href.slice(hashAt) : '';
      var base = hashAt >= 0 ? href.slice(0, hashAt) : href;
      var parts = [];
      utm.forEach(function (item) {
        if (new RegExp('[?&]' + item[0] + '=', 'i').test(base)) return;
        parts.push(encodeURIComponent(item[0]) + '=' + encodeURIComponent(item[1]));
      });
      if (!parts.length) return;
      var joiner = base.indexOf('?') < 0 ? '?' : (/[?&]$/.test(base) ? '' : '&');
      link.setAttribute('href', base + joiner + parts.join('&') + hash);
    }

    function decorateWithin(node) {
      if (!node || !node.querySelectorAll) return;
      if (node.tagName === 'A') decorateLink(node);
      toArray(node.querySelectorAll('a[href]')).forEach(decorateLink);
    }

    decorateWithin(document.body || document.documentElement);

    if (typeof window.MutationObserver === 'function') {
      new MutationObserver(function (records) {
        records.forEach(function (record) {
          if (record.type === 'attributes') decorateLink(record.target);
          else toArray(record.addedNodes).forEach(decorateWithin);
        });
      }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['href'] });
    }

    document.addEventListener('click', function (e) {
      decorateLink(closest(e.target, 'a[href]'));
    }, true);
  }

  /* ---------------------------------------------------------
     5. Yandex Metrika goals (counter is installed by Tilda)
     --------------------------------------------------------- */
  function initGoals() {
    document.addEventListener('click', function (e) {
      var el = closest(e.target, '[data-goal]');
      if (!el) return;
      var goal = el.getAttribute('data-goal');
      if (goal && typeof window.ym === 'function') {
        try { window.ym(94057307, 'reachGoal', goal); } catch (err) { /* ignore */ }
      }
    });
  }

  function start() {
    initAnchors();
    all('[data-carousel]').forEach(initCarousel);
    initPlayer();
    initMusic();
    initPhotos();
    initMediaExclusion();
    initUtm();
    initGoals();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
