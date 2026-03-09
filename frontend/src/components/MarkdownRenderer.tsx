import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

const components: Components = {
  // Style code blocks to match existing dark design
  pre({ children }) {
    return (
      <pre className="bg-gray-100 dark:bg-gray-900 rounded-lg p-4 overflow-x-auto text-sm text-gray-800 dark:text-gray-200">
        {children}
      </pre>
    );
  },
  code({ children, className }) {
    const isInline = !className;
    if (isInline) {
      return (
        <code className="bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 px-1.5 py-0.5 rounded text-sm font-mono">
          {children}
        </code>
      );
    }
    return <code className={`${className ?? ""} font-mono text-gray-800 dark:text-gray-200`}>{children}</code>;
  },
  // Ensure links open safely
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-blue-600 dark:text-blue-400 hover:underline"
      >
        {children}
      </a>
    );
  },
  // Explicit text colors for all content elements
  h1({ children }) {
    return <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-6 mb-3">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-xl font-bold text-gray-900 dark:text-white mt-5 mb-2">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-lg font-semibold text-gray-900 dark:text-white mt-4 mb-2">{children}</h3>;
  },
  h4({ children }) {
    return <h4 className="text-base font-semibold text-gray-900 dark:text-white mt-3 mb-1">{children}</h4>;
  },
  p({ children }) {
    return <p className="text-gray-700 dark:text-gray-300 mb-3 leading-relaxed">{children}</p>;
  },
  li({ children }) {
    return <li className="text-gray-700 dark:text-gray-300 mb-1">{children}</li>;
  },
  strong({ children }) {
    return <strong className="font-semibold text-gray-900 dark:text-white">{children}</strong>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-4 border-gray-300 dark:border-gray-600 pl-4 my-3 text-gray-600 dark:text-gray-400 italic">
        {children}
      </blockquote>
    );
  },
  hr() {
    return <hr className="border-gray-200 dark:border-gray-700 my-6" />;
  },
  // Style tables to match dark theme
  table({ children }) {
    return (
      <div className="overflow-x-auto my-4">
        <table className="min-w-full border border-gray-200 dark:border-gray-600 rounded-lg">
          {children}
        </table>
      </div>
    );
  },
  th({ children }) {
    return (
      <th className="px-4 py-2 bg-gray-100 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-600 text-left text-sm font-semibold text-gray-900 dark:text-white">
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="px-4 py-2 border-b border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-300">
        {children}
      </td>
    );
  },
};

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div
      className={`prose prose-gray dark:prose-invert max-w-none
        prose-headings:text-gray-900 dark:prose-headings:text-white
        prose-p:text-gray-700 dark:prose-p:text-gray-300
        prose-li:text-gray-700 dark:prose-li:text-gray-300
        prose-strong:text-gray-900 dark:prose-strong:text-white
        prose-blockquote:border-gray-300 dark:prose-blockquote:border-gray-600
        ${className ?? ""}`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
