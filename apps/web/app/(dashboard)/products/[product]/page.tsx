import { redirect } from "next/navigation";
import { getProduct, isProduct } from "@/lib/products";
import { ProductContent } from "./_product-content";

export default async function ProductOverviewPage({
  params,
}: {
  params: Promise<{ product: string }>;
}) {
  const { product } = await params;

  if (!isProduct(product)) {
    redirect("/projects");
  }

  if (!getProduct(product).available) {
    redirect(`/products/${product}/coming-soon`);
  }

  return <ProductContent product={product} />;
}
