import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function ApiKeysPage() {
  return (
    <Card className="border-zinc-800 bg-zinc-900">
      <CardHeader className="pb-4">
        <CardTitle className="text-base text-zinc-100">API Keys</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center gap-4 py-10 text-center">
          <svg
            className="h-10 w-10 text-zinc-600"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
          </svg>
          <div>
            <p className="text-sm font-medium text-zinc-300">
              API key management coming in Phase 2
            </p>
            <p className="mt-1 text-sm text-zinc-500">
              Programmatic access to the Testlyn API will be available in a future release.
            </p>
          </div>
          <Button size="sm" disabled>
            Create key
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
