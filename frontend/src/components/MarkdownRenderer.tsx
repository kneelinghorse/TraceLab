import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

const components: Components = {
  input({ type, checked }) {
    // GFM task lists are document content, not editable form controls. Expose
    // the state alongside the task text without an unnamed disabled checkbox.
    if (type === "checkbox") return <span role="img" aria-label={checked ? "Completed" : "Not completed"}>{checked ? "☑" : "☐"}</span>;
    return null;
  },
  // Style code blocks to match existing dark design
  pre({ children }) {
    return (
      <pre className="bg-surface dark:bg-background rounded-lg p-4 overflow-x-auto text-sm text-foreground dark:text-secondary">
        {children}
      </pre>
    );
  },
  code({ children, className }) {
    const isInline = !className;
    if (isInline) {
      return (
        <code className="bg-surface dark:bg-surface-alt text-foreground dark:text-secondary px-1.5 py-0.5 rounded text-sm font-mono">
          {children}
        </code>
      );
    }
    return <code className={`${className ?? ""} font-mono text-foreground dark:text-secondary`}>{children}</code>;
  },
  // Ensure links open safely
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent-text dark:text-accent-text underline underline-offset-4"
      >
        {children}
      </a>
    );
  },
  // Explicit text colors for all content elements
  h1({ children }) {
    return <h1 className="text-2xl font-bold text-foreground dark:text-foreground mt-6 mb-3">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-xl font-bold text-foreground dark:text-foreground mt-5 mb-2">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-lg font-semibold text-foreground dark:text-foreground mt-4 mb-2">{children}</h3>;
  },
  h4({ children }) {
    return <h4 className="text-base font-semibold text-foreground dark:text-foreground mt-3 mb-1">{children}</h4>;
  },
  p({ children }) {
    return <p className="text-secondary dark:text-secondary mb-3 leading-relaxed">{children}</p>;
  },
  li({ children }) {
    return <li className="text-secondary dark:text-secondary mb-1">{children}</li>;
  },
  strong({ children }) {
    return <strong className="font-semibold text-foreground dark:text-foreground">{children}</strong>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-4 border-line-strong dark:border-line-strong pl-4 my-3 text-secondary dark:text-muted italic">
        {children}
      </blockquote>
    );
  },
  hr() {
    return <hr className="border-line dark:border-line my-6" />;
  },
  // Style tables to match dark theme
  table({ children }) {
    return (
      <div tabIndex={0} role="region" aria-label="Scrollable table" className="overflow-x-auto my-4">
        <table className="min-w-full border border-line dark:border-line-strong rounded-lg">
          {children}
        </table>
      </div>
    );
  },
  th({ children }) {
    return (
      <th className="px-4 py-2 bg-surface dark:bg-surface-alt border-b border-line dark:border-line-strong text-left text-sm font-semibold text-foreground dark:text-foreground">
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="px-4 py-2 border-b border-line dark:border-line text-sm text-secondary dark:text-secondary">
        {children}
      </td>
    );
  },
};

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div
      className={`prose prose-gray dark:prose-invert max-w-none
        prose-headings:text-foreground dark:prose-headings:text-foreground
        prose-p:text-secondary dark:prose-p:text-secondary
        prose-li:text-secondary dark:prose-li:text-secondary
        prose-strong:text-foreground dark:prose-strong:text-foreground
        prose-blockquote:border-line-strong dark:prose-blockquote:border-line-strong
        ${className ?? ""}`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
