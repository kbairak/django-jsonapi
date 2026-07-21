import { NavLink, Outlet } from "react-router-dom"

const linkClass = ({ isActive }: { isActive: boolean }) =>
  "block px-3 py-2 rounded-md text-sm font-medium " +
  (isActive ? "bg-slate-700 text-white" : "text-slate-300 hover:bg-slate-700 hover:text-white")

export default function Layout() {
  return (
    <div className="flex h-screen">
      <nav className="w-56 bg-slate-900 flex flex-col shrink-0">
        <div className="h-14 flex items-center px-4 border-b border-slate-700">
          <span className="text-lg font-bold text-white">Articles Admin</span>
        </div>
        <div className="flex-1 p-3 space-y-1">
          <NavLink to="/articles" className={linkClass}>
            Articles
          </NavLink>
          <NavLink to="/categories" className={linkClass}>
            Categories
          </NavLink>
          <NavLink to="/users" className={linkClass}>
            Users
          </NavLink>
        </div>
      </nav>
      <main className="flex-1 overflow-auto bg-slate-50">
        <Outlet />
      </main>
    </div>
  )
}
