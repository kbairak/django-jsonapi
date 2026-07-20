import { DjsonApiSdk } from "./_runtime/sdk.js";
import { Resource } from "./_runtime/resource.js";
import type { SdkConfig } from "./_runtime/sdk.js";
import { Article, Category, User } from "./resources.js";

export class SDK extends DjsonApiSdk {
  static _resourceClasses: Record<string, typeof Resource> = {
    'articles': Article,
    'users': User,
    'categories': Category,
  };

  declare readonly articles: typeof Article;
  declare readonly users: typeof User;
  declare readonly categories: typeof Category;
}

export function createSdk(config: SdkConfig): SDK {
  const sdk = new SDK(config);
  for (const [typeName, cls] of Object.entries(SDK._resourceClasses)) {
    ;(sdk as any)._registry.set(typeName, cls);
    cls._sdk = sdk;
  }
  return new Proxy(sdk, {
    get(target, prop, receiver) {
      if (prop in target || typeof prop === 'symbol') {
        return Reflect.get(target, prop, receiver);
      }
      return target._getResourceClass(prop as string);
    },
  }) as SDK;
}
