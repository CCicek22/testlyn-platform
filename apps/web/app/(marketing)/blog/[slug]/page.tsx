import type { Metadata } from "next";
import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import Link from "next/link";
import { MDXRemote } from "next-mdx-remote/rsc";
import remarkGfm from "remark-gfm";

const CONTENT_DIR = path.join(process.cwd(), "content", "blog");

const VALID_SLUGS = [
  "why-testlyn",
  "agpl-safe-k6",
  "bigquery-streaming-for-load-tests",
] as const;

type ValidSlug = (typeof VALID_SLUGS)[number];

function parseFrontmatter(content: string): Record<string, string> {
  const meta: Record<string, string> = {};
  if (!content.startsWith("---")) return meta;
  const end = content.indexOf("---", 3);
  if (end === -1) return meta;
  const block = content.slice(3, end);
  for (const line of block.split("\n")) {
    const colon = line.indexOf(":");
    if (colon === -1) continue;
    const key = line.slice(0, colon).trim();
    const value = line.slice(colon + 1).trim().replace(/^["']|["']$/g, "");
    meta[key] = value;
  }
  return meta;
}

function stripFrontmatter(content: string): string {
  if (content.startsWith("---")) {
    const end = content.indexOf("---", 3);
    if (end !== -1) return content.slice(end + 3).trimStart();
  }
  return content;
}

function getPost(slug: string): { raw: string; meta: Record<string, string> } | null {
  if (!VALID_SLUGS.includes(slug as ValidSlug)) return null;
  const filePath = path.join(CONTENT_DIR, `${slug}.mdx`);
  if (!fs.existsSync(filePath)) return null;
  const raw = fs.readFileSync(filePath, "utf-8");
  return { raw, meta: parseFrontmatter(raw) };
}

export function generateStaticParams() {
  return VALID_SLUGS.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = getPost(slug);
  if (!post) return { title: "Post not found" };
  return {
    title: post.meta["title"] ?? slug,
    description: post.meta["description"] ?? "",
  };
}

const mdxComponents = {
  h1: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h1 className="mb-6 text-2xl font-bold tracking-tight text-zinc-900" {...props} />
  ),
  h2: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h2 className="mb-3 mt-10 text-xl font-semibold text-zinc-900" {...props} />
  ),
  p: (props: React.HTMLAttributes<HTMLParagraphElement>) => (
    <p className="mb-4 leading-relaxed text-zinc-600" {...props} />
  ),
  ul: (props: React.HTMLAttributes<HTMLUListElement>) => (
    <ul className="mb-4 list-disc space-y-1 pl-5 text-zinc-600" {...props} />
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
  a: (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a
      className="text-primary underline decoration-dotted hover:decoration-solid"
      {...props}
    />
  ),
};

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post = getPost(slug);
  if (!post) notFound();

  const content = stripFrontmatter(post.raw);

  return (
    <div className="mx-auto max-w-3xl px-4 py-20 sm:px-6">
      <nav className="mb-8">
        <Link
          href="/blog"
          className="text-sm text-zinc-500 hover:text-zinc-900 transition-colors"
        >
          &larr; All posts
        </Link>
      </nav>

      {post.meta["date"] && (
        <time
          dateTime={post.meta["date"]}
          className="font-mono text-xs text-zinc-400"
        >
          {post.meta["date"]}
        </time>
      )}

      <article className="mt-2">
        <MDXRemote
          source={content}
          options={{ mdxOptions: { remarkPlugins: [remarkGfm] } }}
          components={mdxComponents}
        />
      </article>

      <div className="mt-12 border-t border-zinc-200 pt-8">
        <Link
          href="/blog"
          className="text-sm text-zinc-500 hover:text-zinc-900 transition-colors"
        >
          &larr; Back to blog
        </Link>
      </div>
    </div>
  );
}
