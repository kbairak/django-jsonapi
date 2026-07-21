import { useQuery } from "@tanstack/react-query";
import { sdk } from "../sdk";

export default function UserList() {
  const users = useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const col = sdk.users.list();
      await col.fetch();
      return [...col];
    },
  });

  if (users.isLoading)
    return <div className="p-6 text-slate-500">Loading…</div>;
  if (users.error)
    return (
      <div className="p-6 text-red-600">{(users.error as Error).message}</div>
    );

  return (
    <div className="p-6 max-w-lg">
      <h1 className="text-xl font-semibold text-slate-800 mb-4">Users</h1>

      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-left">
            <tr>
              <th className="px-4 py-3 font-medium">ID</th>
              <th className="px-4 py-3 font-medium">Username</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {(users.data ?? []).map((u) => (
              <tr key={u.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-slate-500">{u.id}</td>
                <td className="px-4 py-3 text-slate-800">{u.username}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
