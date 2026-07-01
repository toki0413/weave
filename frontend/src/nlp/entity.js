// ============ ENTITY EXTRACTION ============
import { LEXICON, ALL_WORDS } from './lexicon.js';
import { fmmSegment } from './fmm.js';

export function extractEntities(text) {
  var tokens = fmmSegment(text);
  var ent = { persons: [], places: [], events: [], items: [] };
  tokens.forEach(function(t) {
    var cat = t.type + 's';
    if (ent[cat] && ent[cat].indexOf(t.word) < 0) ent[cat].push(t.word);
  });
  return ent;
}

export function extractAnonFeatures(text) {
  var anonMatch = text.match(/那个(.+?)的(?=[，。！？]|$)/) || text.match(/那个(.+)的/);
  if (anonMatch) {
    return anonMatch[1].split(/[、，和]/).map(function(f) { return f.replace(/的/g, '').trim(); }).filter(function(f) { return f.length > 0; });
  }
  return [];
}
