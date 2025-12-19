/**
 * Research Export Utilities
 *
 * Functions for exporting research results to various formats:
 * - Markdown (with academic-style citations)
 * - JSON (raw structured data)
 * - PDF (via html2pdf.js)
 * - Copy to clipboard
 */

import type { SessionResults, Finding } from '../../../types/research';

/**
 * Generate a markdown report from research results.
 * Follows academic report structure with citations.
 */
export function generateMarkdown(results: SessionResults): string {
  const lines: string[] = [
    `# Research Report`,
    '',
    `> ${results.query}`,
    '',
    '---',
    '',
    '## Summary',
    '',
    `| Metric | Value |`,
    `|--------|-------|`,
    `| Status | ${results.status} |`,
    `| Findings | ${results.total_findings} |`,
    `| Sources | ${results.total_sources} |`,
    `| Cost | $${results.total_cost_usd.toFixed(4)} |`,
    results.completeness_score !== null
      ? `| Completeness | ${(results.completeness_score * 100).toFixed(0)}% |`
      : '',
    results.confidence_score !== null
      ? `| Confidence | ${(results.confidence_score * 100).toFixed(0)}% |`
      : '',
    '',
  ].filter(Boolean);

  // Synthesis section
  lines.push('## Synthesis', '');
  if (results.final_synthesis) {
    lines.push(results.final_synthesis);
  } else {
    lines.push('_No synthesis available. Generate one from the Results tab._');
  }
  lines.push('');

  // Findings section
  if (results.findings.length > 0) {
    lines.push('## Findings', '');

    results.findings.forEach((finding, index) => {
      lines.push(
        `### ${index + 1}. ${capitalize(finding.finding_type)} ` +
          `(${(finding.confidence * 100).toFixed(0)}% confidence)`
      );
      lines.push('');
      lines.push(finding.content);
      lines.push('');

      if (finding.sources && finding.sources.length > 0) {
        lines.push('**Sources:**');
        finding.sources.forEach((source) => {
          const title = source.title || new URL(source.url).hostname;
          lines.push(`- [${title}](${source.url})`);
        });
        lines.push('');
      }
    });
  }

  // Footer
  lines.push('---', '');
  lines.push(`*Generated on ${new Date().toLocaleDateString()} by KITTY Research*`);

  return lines.join('\n');
}

/**
 * Helper to capitalize first letter.
 */
function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Trigger a file download in the browser.
 */
export function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Export research results as Markdown file.
 */
export function exportMarkdown(results: SessionResults): void {
  const md = generateMarkdown(results);
  const filename = `research-${results.session_id.slice(0, 8)}.md`;
  downloadFile(md, filename, 'text/markdown');
}

/**
 * Export research results as JSON file.
 */
export function exportJSON(results: SessionResults): void {
  const json = JSON.stringify(results, null, 2);
  const filename = `research-${results.session_id.slice(0, 8)}.json`;
  downloadFile(json, filename, 'application/json');
}

/**
 * Copy research results (as markdown) to clipboard.
 * Returns true on success, false on failure.
 */
export async function copyToClipboard(results: SessionResults): Promise<boolean> {
  const md = generateMarkdown(results);
  try {
    await navigator.clipboard.writeText(md);
    return true;
  } catch (error) {
    console.error('Failed to copy to clipboard:', error);
    return false;
  }
}

/**
 * Export research results as PDF file.
 * Requires html2pdf.js to be installed.
 */
export async function exportPDF(results: SessionResults): Promise<void> {
  // Dynamic import to avoid bundling if not used
  const html2pdf = (await import('html2pdf.js')).default;

  const md = generateMarkdown(results);

  // Create a styled container for PDF rendering
  const container = document.createElement('div');
  container.style.cssText = `
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 12px;
    line-height: 1.6;
    color: #333;
    padding: 20px;
    max-width: 800px;
  `;

  // Convert markdown to HTML (basic conversion)
  const html = markdownToHtml(md);
  container.innerHTML = html;

  // Generate PDF with options
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const pdfOptions: any = {
    margin: 10,
    filename: `research-${results.session_id.slice(0, 8)}.pdf`,
    image: { type: 'jpeg', quality: 0.98 },
    html2canvas: { scale: 2 },
    jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
  };

  await html2pdf().set(pdfOptions).from(container).save();
}

/**
 * Basic markdown to HTML conversion for PDF export.
 * Handles common markdown patterns.
 */
function markdownToHtml(md: string): string {
  return (
    md
      // Headers
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      // Bold
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      // Italic/emphasis
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/_(.+?)_/g, '<em>$1</em>')
      // Links
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
      // Blockquotes
      .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
      // Horizontal rules
      .replace(/^---$/gm, '<hr>')
      // Tables (basic)
      .replace(/\|(.+)\|/g, (match) => {
        const cells = match
          .split('|')
          .filter(Boolean)
          .map((cell) => cell.trim());
        if (cells.every((c) => c.match(/^-+$/))) {
          return ''; // Table separator row
        }
        return '<tr>' + cells.map((c) => `<td>${c}</td>`).join('') + '</tr>';
      })
      // List items
      .replace(/^- (.+)$/gm, '<li>$1</li>')
      // Paragraphs (double newlines)
      .replace(/\n\n/g, '</p><p>')
      // Wrap in paragraphs
      .replace(/^(.+)$/gm, (match) => {
        if (
          match.startsWith('<') ||
          match.startsWith('|') ||
          match.trim() === ''
        ) {
          return match;
        }
        return `<p>${match}</p>`;
      })
  );
}
