// app/layout.tsx
// app/layout.tsx
import "./globals.css";

export const metadata = { title: "NFL Fantasy Champs" };
export const viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[--background] text-[--foreground]">
        {children}
      </body>
    </html>
  );
}

