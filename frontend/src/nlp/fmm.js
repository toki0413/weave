// ============ FMM ============
import { ALL_WORDS } from './lexicon.js';

function fmmSegment(text) {
  var result = [], i = 0;
  while (i < text.length) {
    var matched = false;
    for (var j = Math.min(6, text.length - i); j >= 2; j--) {
      var sub = text.substring(i, i + j);
      for (var k = 0; k < ALL_WORDS.length; k++) {
        if (ALL_WORDS[k].word === sub) {
          result.push({ word: sub, type: ALL_WORDS[k].type, start: i, end: i + j });
          i += j; matched = true; break;
        }
      }
      if (matched) break;
    }
    if (!matched) i++;
  }
  // Priority-based overlap resolution: place > item > event > person
  var priority = { place: 4, item: 3, event: 2, person: 1 };
  var filtered = [];
  result.forEach(function(t) {
    var overlap = false;
    for (var i = 0; i < filtered.length; i++) {
      var f = filtered[i];
      if (t.start < f.end && t.end > f.start) {
        if (priority[t.type] > priority[f.type]) {
          filtered[i] = t;
        }
        overlap = true; break;
      }
    }
    if (!overlap) filtered.push(t);
  });
  return filtered;
}

export { fmmSegment };
