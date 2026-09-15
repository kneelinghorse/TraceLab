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
  // Code uses the same semantic surfaces in every theme.
  pre({ children }) {
    return (
      <pre className="bg-surface rounded-lg p-4 overflow-x-auto text-sm text-foreground">
        {children}
      </pre>
    );
  },
  code({ children, className }) {
    const isInline = !className;
    if (isInline) {
      return (
        <code className="bg-surface text-foreground px-1.5 py-0.5 rounded text-sm font-mono">
          {children}
        </code>
      );
    }
    return <code className={`${className ?? ""} font-mono text-foreground`}>{children}</code>;
  },
  // Ensure links open safely
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent-text underline underline-offset-4"
      >
        {children}
      </a>
    );
  },
  // Explicit text colors for all content elements
  h1({ children }) {
    return <h1 className="text-2xl font-bold text-foreground mt-6 mb-3">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-xl font-bold text-foreground mt-5 mb-2">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-lg font-semibold text-foreground mt-4 mb-2">{children}</h3>;
  },
  h4({ children }) {
    return <h4 className="text-base font-semibold text-foreground mt-3 mb-1">{children}</h4>;
  },
  p({ children }) {
    return <p className="text-secondary mb-3 leading-relaxed">{children}</p>;
  },
  li({ children }) {
    return <li className="text-secondary mb-1">{children}</li>;
  },
  strong({ children }) {
    return <strong className="font-semibold text-foreground">{children}</strong>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-4 border-line-strong pl-4 my-3 text-secondary italic">
        {children}
      </blockquote>
    );
  },
  hr() {
    return <hr className="border-line my-6" />;
  },
  // Keep wide tables readable without overflowing the page. Cells opt out of the
  // shell's overflow-wrap:anywhere so columns keep whole words and the region scrolls.
  table({ children }) {
    return (
      <div tabIndex={0} role="region" aria-label="Scrollable table" className="overflow-x-auto my-4">
        <table className="min-w-full border border-line rounded-lg">
          {children}
        </table>
      </div>
    );
  },
  th({ children }) {
    return (
      <th className="px-4 py-2 bg-surface border-b border-line text-left text-sm font-semibold text-foreground break-normal">
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="px-4 py-2 border-b border-line text-sm text-secondary break-normal">
        {children}
      </td>
    );
  },
};

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div
      className={`prose prose-tokens max-w-none
        prose-headings:text-foreground
        prose-p:text-secondary
        prose-li:text-secondary
        prose-strong:text-foreground
        prose-blockquote:border-line-strong
        ${className ?? ""}`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
