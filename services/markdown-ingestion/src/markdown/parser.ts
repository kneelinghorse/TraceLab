import { readFile } from 'fs/promises';
import matter from 'gray-matter';

export interface ParsedMarkdown {
  content: string;
  frontMatter: Record<string, unknown>;
}

export const parseMarkdownFile = async (path: string): Promise<ParsedMarkdown> => {
  const fileContent = await readFile(path, 'utf-8');
  const parsed = matter(fileContent);
  return {
    content: parsed.content,
    frontMatter: parsed.data ?? {},
  };
};
