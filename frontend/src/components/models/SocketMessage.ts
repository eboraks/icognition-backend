export class SocketMessage {
    message: string | null;
    self: string | null;
    user_uuid: string | null;

    constructor(
        message: string | null,
        self: string | null,
        user_uuid: string | null
    ) {
        this.message = message;
        this.self = self;
        this.user_uuid = user_uuid;
    }
}