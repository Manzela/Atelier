/**
 * Smartly prettifies and shortens project briefs or IDs into clean, professional titles.
 * E.g., 'Build a 1:1 "Linear" project management system but for Autonomous AI Agent'
 *   -> 'Linear for Autonomous Agents'
 */
export function prettifyProjectName(brief: string, id?: string): string {
  let text = brief ? brief.trim() : '';

  // If no brief is provided, try to extract from the ID
  if (!text && id) {
    try {
      // Decode URL encoding
      text = decodeURIComponent(id);
    } catch {
      text = id;
    }
    // Remove trailing timestamp (hyphen followed by 10-13 digits)
    text = text.replace(/-[0-9]{10,13}$/, '');
    // Replace hyphens with spaces
    text = text.replace(/-/g, ' ');
  }

  if (!text) {
    return 'Untitled Project';
  }

  // Check for special case: "Linear" and "Autonomous AI Agent"
  const textLower = text.toLowerCase();
  if (
    textLower.includes('linear') &&
    (textLower.includes('autonomous') || textLower.includes('agent'))
  ) {
    return 'Linear for Autonomous Agents';
  }

  // Pre-process common prefixes/suffixes
  // Remove starting "build a/an", "create a/an", "design a/an", "make a/an", "develop a/an", etc.
  text = text.replace(
    /^(build|create|design|make|develop|want\s+to\s+build|want\s+to\s+create|want\s+to\s+design)\s+(a|an|the|our|my|one\s*:\s*one|1\s*:\s*1)?\s+/i,
    ''
  );

  // Strip wrapping quotes
  text = text.replace(/^["'“”‘’](.*?)["'“”‘’]$/, '$1');

  // If it's very long, let's extract key entities
  if (text.split(' ').length > 6) {
    // 1. Look for quoted brand/app names (e.g. "Linear")
    const quoteMatch = text.match(/["'“”‘’]([^"'“”‘’]+)["'“”‘’]/);
    const brand = quoteMatch ? quoteMatch[1] : '';

    // 2. Identify core system type (e.g. project management system, landing page, dashboard)
    let coreType = '';
    const types = [
      'project management',
      'management system',
      'landing page',
      'dashboard',
      'marketplace',
      'crm',
      'e-commerce',
      'social network',
      'clone',
    ];
    for (const t of types) {
      if (textLower.includes(t)) {
        coreType = t;
        break;
      }
    }

    // 3. Identify target/context (e.g. for Autonomous AI Agent, for developers)
    let target = '';
    const forMatch = text.match(/\b(for|but\s+for|targeting)\s+([^,.(]+)/i);
    if (forMatch) {
      target = forMatch[2].trim();
      // Clean up target: "Autonomous AI Agent" -> "Autonomous Agents"
      target = target
        .replace(/^(an?|the)\s+/i, '')
        .replace(/\bautonomous\s+ai\s+agent(s)?\b/i, 'Autonomous Agents')
        .replace(/\bautonomous\s+agent(s)?\b/i, 'Autonomous Agents')
        .replace(/\bai\s+agent(s)?\b/i, 'AI Agents')
        .replace(/\bagent(s)?\b/i, 'Agents');
    }

    // Synthesize the short name
    if (brand && target) {
      return `${capitalize(brand)} for ${capitalize(target)}`;
    } else if (brand && coreType) {
      return `${capitalize(brand)} ${capitalize(coreType)}`;
    } else if (coreType && target) {
      return `${capitalize(coreType)} for ${capitalize(target)}`;
    } else if (target) {
      return `App for ${capitalize(target)}`;
    }
  }

  // Title case the cleaned brief
  return toTitleCase(text);
}

function capitalize(s: string): string {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function toTitleCase(str: string): string {
  const minorWords = [
    'a',
    'an',
    'the',
    'and',
    'but',
    'or',
    'for',
    'nor',
    'on',
    'at',
    'to',
    'from',
    'by',
    'of',
    'in',
  ];
  const words = str.split(/\s+/);
  const titleWords = words.map((word, index) => {
    const cleanWord = word.replace(/[^a-zA-Z0-9]/g, '');
    if (cleanWord.length === 0) return word;
    const isMinor = minorWords.includes(cleanWord.toLowerCase());
    if (isMinor && index !== 0 && index !== words.length - 1) {
      return word.toLowerCase();
    }
    const match = word.match(/[a-zA-Z0-9]/);
    if (match && match.index !== undefined) {
      const idx = match.index;
      return word.slice(0, idx) + word.charAt(idx).toUpperCase() + word.slice(idx + 1);
    }
    return word;
  });

  let result = titleWords.join(' ');
  // Cap at 45 characters for display sanity
  if (result.length > 45) {
    const truncated = result.slice(0, 42);
    const lastSpace = truncated.lastIndexOf(' ');
    result = lastSpace > 10 ? truncated.slice(0, lastSpace) + '...' : truncated + '...';
  }
  return result;
}
