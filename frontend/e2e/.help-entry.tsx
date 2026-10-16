
import { renderToStaticMarkup } from "react-dom/server";
import { GuideContent } from "@/routes/guide";
import { UseCasesContent } from "@/routes/use-cases";
import { FaqContent } from "@/routes/faq";
import { METRICS } from "@/components/docs/MetricsChart";

globalThis.__metricHelp = METRICS;
globalThis.__help = {
  "/guide": renderToStaticMarkup(<GuideContent />),
  "/use-cases": renderToStaticMarkup(<UseCasesContent />),
  "/faq": renderToStaticMarkup(<FaqContent />),
};
