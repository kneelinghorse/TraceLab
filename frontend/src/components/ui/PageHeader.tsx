import type { ReactNode } from "react";

export function PageContainer({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-7xl space-y-4 px-4 py-5 sm:px-6 [&_.form-label]:text-sm [&_.text-xs]:text-sm">{children}</div>;
}

export function PageHeader({ title, description, actions, children }: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return <header className="space-y-2">
    <div className="flex flex-col items-stretch gap-x-4 gap-y-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-1 flex-col items-start gap-x-4 gap-y-1 sm:flex-row sm:flex-wrap sm:items-baseline">
        <h1 className="break-words text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description && <p className="min-w-0 flex-1 break-words text-secondary sm:min-w-48">{description}</p>}
      </div>
      {actions && <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div>}
    </div>
    {children}
  </header>;
}
