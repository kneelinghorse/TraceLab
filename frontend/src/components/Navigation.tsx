/**
 * Main navigation component
 */

import Link from "next/link";
import { useRouter } from "next/router";

export function Navigation() {
  const router = useRouter();

  const isActive = (path: string) => {
    return router.pathname.startsWith(path);
  };

  return (
    <nav className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-8">
            <Link href="/" className="text-xl font-bold text-gray-900 dark:text-white">
              TraceLab
            </Link>
            <div className="flex gap-4">
              <Link
                href="/documents"
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive("/documents")
                    ? "bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
                }`}
              >
                Documents
              </Link>
              <Link
                href="/missions"
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive("/missions")
                    ? "bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
                }`}
              >
                Missions
              </Link>
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}

