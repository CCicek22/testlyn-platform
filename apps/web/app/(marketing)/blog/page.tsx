import type { Metadata } from "next";
import fs from "node:fs";
import path from "node:path";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Blog",
  description: "Engineering posts from the Testlyn team.",
};

type PostMeta = {
  slug: string;
  title: string;
  date: string;
  description: string;
};

const CONTENT_DIR = path.join(process.cwd(), "content", "blog");

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

function getPosts(): PostMeta[] {
  const files = fs.readdirSync(CONTENT_DIR).filter((f) => f.endsWith(".mdx"));
  return files
    .map((file) => {
      const raw = fs.readFileSync(path.join(CONTENT_DIR, file), "utf-8");
      const meta = parseFrontmatter(raw);
      return {
        slug: file.replace(/\.mdx$/, ""),
        title: meta["title"] ?? file,
        date: meta["date"] ?? "",
        description: meta["description"] ?? "",
      };
    })
    .sort((a, b) => b.date.localeCompare(a.date));
}

export default function BlogIndexPage() {
  const posts = getPosts();

  return (
    <div className="mx-auto max-w-3xl px-4 py-20 sm:px-6">
      <h1 className="mb-2 text-3xl font-bold tracking-tight text-zinc-900">
        Blog
      </h1>
      <p className="mb-12 text-zinc-500">
        Engineering posts from the Testlyn team. Dev-to-dev, no fluff.
      </p>

      <ul className="space-y-8">
        {posts.map((post) => (
          <li key={post.slug}>
            <article>
              <time
                dateTime={post.date}
                className="font-mono text-xs text-zinc-400"
              >
                {post.date}
              </time>
              <h2 className="mt-1 text-lg font-semibold text-zinc-900">
                <Link
                  href={`/blog/${post.slug}`}
                  className="hover:text-primary transition-colors"
                >
                  {post.title}
                </Link>
              </h2>
              <p className="mt-1 text-sm leading-relaxed text-zinc-500">
                {post.description}
              </p>
              <Link
                href={`/blog/${post.slug}`}
                className="mt-2 inline-block text-sm font-medium text-primary hover:underline"
              >
                Read more &rarr;
              </Link>
            </article>
          </li>
        ))}
      </ul>
    </div>
  );
}
