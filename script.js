/* Shagai pod hity landing. Vanilla JS, no dependencies. ASCII only. */
(function () {
  'use strict';

  var root = document.querySelector('.hits');
  if (!root) return;

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

  /* ---------------------------------------------------------
     1. Smooth anchor scroll (own rAF animation)
     --------------------------------------------------------- */
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

  root.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var link = closest(e.target, 'a[href]');
    if (!link) return;
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

  /* ---------------------------------------------------------
     2. Tariffs carousel (mobile): snap + dots + rAF animation
     --------------------------------------------------------- */
  function initCarousel(box) {
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

  toArray(root.querySelectorAll('[data-carousel]')).forEach(initCarousel);

  /* ---------------------------------------------------------
     3. Format player: image -> <video> when data-video is set
     --------------------------------------------------------- */
  function initPlayer() {
    var player = root.querySelector('.hits-player');
    if (!player) return;

    function playVideo(src) {
      src = (src || '').replace(/^\s+|\s+$/g, '');
      if (!src) return false;
      var video = player.querySelector('video');
      if (!video) {
        video = document.createElement('video');
        video.setAttribute('controls', '');
        video.setAttribute('playsinline', '');
        video.setAttribute('preload', 'auto');
        video.playsInline = true;
        var img = player.querySelector('img');
        if (img && img.currentSrc) video.setAttribute('poster', img.currentSrc);
        if (img && img.alt) video.setAttribute('aria-label', img.alt);
        var media = player.querySelector('picture') || img;
        if (media && media.parentNode) media.parentNode.replaceChild(video, media);
        else player.appendChild(video);
      }
      if (video.getAttribute('src') !== src) video.setAttribute('src', src);
      var promise = video.play();
      if (promise && typeof promise.catch === 'function') promise.catch(function () { /* autoplay blocked */ });
      return true;
    }

    player.addEventListener('click', function () {
      if (!player.querySelector('video')) playVideo(player.getAttribute('data-video'));
    });

    toArray(root.querySelectorAll('[data-track]')).forEach(function (row, index, rows) {
      var button = row.querySelector('.hits-play');
      if (!button) return;
      button.addEventListener('click', function () {
        if (!playVideo(row.getAttribute('data-video'))) return;
        rows.forEach(function (other) {
          var isActive = other === row;
          other.classList.toggle('is-active', isActive);
          var otherButton = other.querySelector('.hits-play');
          if (otherButton) otherButton.classList.toggle('hits-play--active', isActive);
        });
      });
    });
  }

  initPlayer();

  /* ---------------------------------------------------------
     4. UTM passthrough to walk-walk.ru links
     --------------------------------------------------------- */
  var UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'erid'];

  function readUtm() {
    var found = [];
    var query = window.location.search.replace(/^\?/, '');
    if (!query) return found;
    var map = {};
    query.split('&').forEach(function (pair) {
      if (!pair) return;
      var eq = pair.indexOf('=');
      var rawKey = eq >= 0 ? pair.slice(0, eq) : pair;
      var rawValue = eq >= 0 ? pair.slice(eq + 1) : '';
      var key;
      var value;
      try {
        key = decodeURIComponent(rawKey.replace(/\+/g, ' '));
        value = decodeURIComponent(rawValue.replace(/\+/g, ' '));
      } catch (err) { return; }
      if (value && !(key in map)) map[key] = value;
    });
    UTM_KEYS.forEach(function (key) {
      if (map[key]) found.push([key, map[key]]);
    });
    return found;
  }

  var utm = readUtm();

  function isWalkWalk(href) {
    var match = /^(?:https?:)?\/\/([^\/?#:]+)/i.exec(href);
    if (!match) return false;
    var host = match[1].toLowerCase();
    return host === 'walk-walk.ru' || host.slice(-13) === '.walk-walk.ru';
  }

  function decorateLink(link) {
    if (!utm.length || !link || link.nodeType !== 1 || link.tagName !== 'A') return;
    var href = link.getAttribute('href') || '';
    if (!isWalkWalk(href) || /[?&]utm_/i.test(href)) return;
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

  if (utm.length) {
    decorateWithin(document.body || document.documentElement);

    if (typeof window.MutationObserver === 'function') {
      new MutationObserver(function (records) {
        records.forEach(function (record) {
          if (record.type === 'attributes') {
            decorateLink(record.target);
          } else {
            toArray(record.addedNodes).forEach(decorateWithin);
          }
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
  document.addEventListener('click', function (e) {
    var el = closest(e.target, '[data-goal]');
    if (!el) return;
    var goal = el.getAttribute('data-goal');
    if (goal && typeof window.ym === 'function') {
      try { window.ym(94057307, 'reachGoal', goal); } catch (err) { /* ignore */ }
    }
  });
})();
