import type { Metadata } from "next";
import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import { MDXRemote } from "next-mdx-remote/rsc";
import remarkGfm from "remark-gfm";
import Link from "next/link";

// ── Sidebar nav definition (order-sensitive) ──────────────────────────────
const SIDEBAR_SECTIONS = [
  {
    label: "Getting started",
    items: [
      { slug: "", title: "Quickstart" },
    ],
  },
  {
    label: "Reference",
    items: [
      { slug: "k6-script-reference", title: "k6 Script Reference" },
      { slug: "api-auth", title: "API Authentication" },
    ],
  },
] as const;

// Map slug → filename in content/docs/
const SLUG_TO_FILE: Record<string, string> = {
  "": "quickstart.mdx",
  "k6-script-reference": "k6-script-reference.mdx",
  "api-auth": "api-auth.mdx",
};

const CONTENT_DIR = path.join(process.cwd(), "content", "docs");

function getMdxContent(slug: string): string | null {
  const filename = SLUG_TO_FILE[slug];
  if (!filename) return null;
  const filePath = path.join(CONTENT_DIR, filename);
  if (!fs.existsSync(filePath)) return null;
  return fs.readFileSync(filePath, "utf-8");
}

function stripFrontmatter(content: string): string {
  if (content.startsWith("---")) {
    const end = content.indexOf("---", 3);
    if (end !== -1) return content.slice(end + 3).trimStart();
  }
  return content;
}

function getTitleFromContent(content: string): string {
  const match = content.match(/^title:\s*["']?(.+?)["']?\s*$/m);
  return match?.[1] ?? "Documentation";
}

export async function generateStaticParams() {
  return Object.keys(SLUG_TO_FILE).map((slug) => ({
    slug: slug === "" ? [] : slug.split("/"),
  }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const slugStr = slug?.join("/") ?? "";
  const raw = getMdxContent(slugStr);
  if (!raw) return { title: "Docs" };
  const title = getTitleFromContent(raw);
  return { title };
}

// MDX components — prose styles applied via className wrapper
const components = {
  h1: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h1 className="mb-6 text-2xl font-bold tracking-tight text-zinc-900" {...props} />
  ),
  h2: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h2 className="mb-3 mt-10 text-xl font-semibold text-zinc-900" {...props} />
  ),
  h3: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h3 className="mb-2 mt-6 text-base font-semibold text-zinc-900" {...props} />
  ),
  p: (props: React.HTMLAttributes<HTMLParagraphElement>) => (
    <p className="mb-4 leading-relaxed text-zinc-600" {...props} />
  ),
  ul: (props: React.HTMLAttributes<HTMLUListElement>) => (
    <ul className="mb-4 list-disc space-y-1 pl-5 text-zinc-600" {...props} />
  ),
  ol: (props: React.HTMLAttributes<HTMLOListElement>) => (
    <ol className="mb-4 list-decimal space-y-1 pl-5 text-zinc-600" {...props} />
  ),
  li: (props: React.HTMLAttributes<HTMLLIElement>) => (
    <li className="text-sm leading-relaxed" {...props} />
  ),
  code: (props: React.HTMLAttributes<HTMLElement>) => (
    <code
      className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-xs text-zinc-800"
      {...props}
    />
  ),
  pre: (props: React.HTMLAttributes<HTMLPreElement>) => (
    <pre
      className="mb-6 overflow-x-auto rounded-lg bg-zinc-900 p-4 text-xs text-zinc-300"
      {...props}
    />
  ),
  table: (props: React.HTMLAttributes<HTMLTableElement>) => (
    <div className="mb-6 overflow-x-auto rounded-lg border border-zinc-200">
      <table className="w-full text-sm" {...props} />
    </div>
  ),
  th: (props: React.HTMLAttributes<HTMLTableCellElement>) => (
    <th
      className="border-b border-zinc-200 bg-zinc-50 px-4 py-2 text-left font-semibold text-zinc-900"
      {...props}
    />
  ),
  td: (props: React.HTMLAttributes<HTMLTableCellElement>) => (
    <td className="border-b border-zinc-100 px-4 py-2 text-zinc-600" {...props} />
  ),
  a: (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a
      className="text-primary underline decoration-dotted hover:decoration-solid"
      {...props}
    />
  ),
};

export default async function DocsPage({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}) {
  const { slug } = await params;
  const slugStr = slug?.join("/") ?? "";
  const raw = getMdxContent(slugStr);

  if (!raw) notFound();

  const content = stripFrontmatter(raw);

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
      <div className="flex gap-10">
        {/* Sidebar */}
        <aside className="hidden w-52 shrink-0 lg:block">
          <nav aria-label="Documentation navigation">
            {SIDEBAR_SECTIONS.map((section) => (
              <div key={section.label} className="mb-6">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                  {section.label}
                </p>
                <ul className="space-y-1">
                  {section.items.map((item) => {
                    const href = item.slug === "" ? "/docs" : `/docs/${item.slug}`;
                    const isActive = slugStr === item.slug;
                    return (
                      <li key={item.slug}>
                        <Link
                          href={href}
                          className={`block rounded-md px-2 py-1.5 text-sm transition-colors ${
                            isActive
                              ? "bg-primary/5 font-medium text-primary"
                              : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
                          }`}
                        >
                          {item.title}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
        </aside>

        {/* Content */}
        <article className="min-w-0 flex-1">
          <MDXRemote
            source={content}
            options={{ mdxOptions: { remarkPlugins: [remarkGfm] } }}
            components={components}
          />
        </article>
      </div>
    </div>
  );
}
