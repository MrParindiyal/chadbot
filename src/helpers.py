from pathlib import Path

def is_user_approved(username):
    try:
        with open("./data/approved.txt", "r") as f:
            approved_users = [line.strip() for line in f if line.strip()]
            return username in approved_users

    except FileNotFoundError:
        return False


def whitelist_user(username):
    if is_user_approved(username):
        return False
    
    with open("./data/approved.txt", "a") as f:
        f.write(f"{username}\n")

    return True

def remove_whitelisted_user(username):
    if not is_user_approved(username):
        return False
    
    with open("./data/approved.txt", "r") as f:
        users = [line.strip() for line in f if line.strip()]
    
    users.remove(username)

    with open("./data/approved.txt", "w") as f:
        for user in users:
            f.write(f"{user}\n")
    
    return True