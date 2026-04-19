import { type ImgHTMLAttributes, useState } from "react";
import { BRAND_FALLBACK_ICON_PATH, BRAND_LOGO_PATH } from "@/lib/branding";

type BrandLogoProps = Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> & {
  fallbackSrc?: string;
};

export function BrandLogo({
  alt = "Nifty Node",
  fallbackSrc = BRAND_FALLBACK_ICON_PATH,
  onError,
  ...props
}: BrandLogoProps) {
  const [src, setSrc] = useState(BRAND_LOGO_PATH);

  return (
    <img
      {...props}
      alt={alt}
      src={src}
      onError={(event) => {
        if (src !== fallbackSrc) {
          setSrc(fallbackSrc);
        }
        onError?.(event);
      }}
    />
  );
}
