import { sdk } from "./articles_sdk/index.js";
sdk.setup({ host: "http://localhost:8000/api/" });
export { sdk };
