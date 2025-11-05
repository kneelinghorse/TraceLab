import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkFrontmatter from 'remark-frontmatter';
import remarkGfm from 'remark-gfm';
import { toString } from 'mdast-util-to-string';
import { toMarkdown } from 'mdast-util-to-markdown';
import { visit } from 'unist-util-visit';
import type { Content, Heading, Root } from 'mdast';

import type { MarkdownChunk } from '../types.js';
import { sha256 } from '../utils/hash.js';

export interface ChunkerOptions {
  minCharacters: number;
  maxCharacters: number;
  overlapCharacters: number;
}

const processor = unified()
  .use(remarkParse)
  .use(remarkFrontmatter as unknown as any, ['yaml', 'toml'])
  .use(remarkGfm as unknown as any);

const cloneNodes = (nodes: Content[]): Content[] => JSON.parse(JSON.stringify(nodes));

const updateHeadingTrail = (node: Heading, trail: string[]): string[] => {
  const next = [...trail];
  const headingText = toString(node).trim();
  next.splice(node.depth - 1);
  next[node.depth - 1] = headingText;
  return next;
};

const createChunk = (
  nodes: Content[],
  headingTrail: string[],
  chunkIndex: number,
  options: ChunkerOptions,
): MarkdownChunk | undefined => {
  if (nodes.length === 0) {
    return undefined;
  }
  const root: Root = { type: 'root', children: cloneNodes(nodes) };
  const markdown = toMarkdown(root).trim();
  const plainText = toString(root).trim();
  if (!plainText || plainText.length < options.minCharacters) {
    return undefined;
  }
  return {
    chunkIndex,
    chunkHash: sha256(`${headingTrail.join('>')}::${markdown}`),
    headingTrail,
    content: markdown,
    textForEmbedding: plainText,
    chunkId: '',
  };
};

const splitOversizedChunk = (
  chunk: MarkdownChunk,
  options: ChunkerOptions,
): MarkdownChunk[] => {
  if (chunk.textForEmbedding.length <= options.maxCharacters) {
    return [chunk];
  }

  const paragraphs = chunk.content.split(/\n\s*\n/g);
  const results: MarkdownChunk[] = [];
  let buffer = '';
  let bufferPlain = '';
  let index = 0;

  const flush = () => {
    const trimmed = buffer.trim();
    const textTrimmed = bufferPlain.trim();
    if (!trimmed || textTrimmed.length < options.minCharacters) {
      buffer = '';
      bufferPlain = '';
      return;
    }
    results.push({
      ...chunk,
      chunkIndex: chunk.chunkIndex + index,
      chunkHash: sha256(`${chunk.headingTrail.join('>')}::${trimmed}::${index}`),
      content: trimmed,
      textForEmbedding: textTrimmed,
      chunkId: '',
    });
    index += 1;
    if (options.overlapCharacters > 0) {
      const overlapSource = textTrimmed.slice(-options.overlapCharacters);
      buffer = `${overlapSource}\n\n`;
      bufferPlain = overlapSource;
    } else {
      buffer = '';
      bufferPlain = '';
    }
  };

  for (const paragraph of paragraphs) {
    const candidate = buffer.length > 0 ? `${buffer}\n\n${paragraph}` : paragraph;
    if (candidate.length > options.maxCharacters && buffer.length > 0) {
      flush();
    }
    buffer = buffer.length > 0 ? `${buffer}\n\n${paragraph}` : paragraph;
    bufferPlain = bufferPlain.length > 0 ? `${bufferPlain}\n\n${paragraph}` : paragraph;
  }
  flush();

  return results;
};

export const chunkMarkdown = (
  markdown: string,
  options: ChunkerOptions,
): MarkdownChunk[] => {
  const tree = processor.parse(markdown) as Root;
  const chunks: MarkdownChunk[] = [];
  let currentNodes: Content[] = [];
  let headingTrail: string[] = [];
  let chunkIndex = 0;

  const flush = () => {
    const baseChunk = createChunk(currentNodes, headingTrail, chunkIndex, options);
    if (baseChunk) {
      const split = splitOversizedChunk(baseChunk, options);
      split.forEach((chunk, idx) => {
        chunks.push({
          ...chunk,
          chunkIndex: chunkIndex + idx,
        });
      });
      chunkIndex += split.length;
    }
    currentNodes = [];
  };

  for (const node of tree.children) {
    if (node.type === 'heading') {
      if (currentNodes.length > 0) {
        flush();
      }
      headingTrail = updateHeadingTrail(node as Heading, headingTrail);
      currentNodes.push(node);
      continue;
    }
    if (node.type === 'thematicBreak') {
      currentNodes.push(node);
      flush();
      continue;
    }
    currentNodes.push(node);
  }

  flush();

  // assign deterministic IDs placeholder (populated later)
  return chunks.map((chunk) => ({
    ...chunk,
    chunkId: chunk.chunkId,
  }));
};
