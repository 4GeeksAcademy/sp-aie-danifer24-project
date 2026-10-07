"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { clearStoredAccessToken, getStoredAccessToken } from "@/lib/auth";

export default function LogoutButton() {
  const pathname = usePathname();
  const router = useRouter();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    function updateVisibility() {
      if (pathname === "/login" || pathname === "/register") {
        setVisible(false);
        return;
      }
      try {
        setVisible(Boolean(getStoredAccessToken()));
      } catch {
        setVisible(false);
      }
    }

    updateVisibility();
    window.addEventListener("storage", updateVisibility);
    return () => window.removeEventListener("storage", updateVisibility);
  }, [pathname]);

  function logout() {
    clearStoredAccessToken();
    setVisible(false);
    router.replace("/login");
  }

  if (!visible) return null;

  return <button type="button" className="secondary-button logout-button" onClick={logout} title="Cerrar sesión"><LogOut size={17} /> Cerrar sesión</button>;
}