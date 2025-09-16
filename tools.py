import time

"""TOOLS"""
def move(location: str) -> str:
    """
    You can choose to move your character to a certain waypoint in the village. Your only options are as follows: Willem's house, The Prancing Pony Inn, The tavern
    """
    valid_locations = [
        "Willem's house",
        "The Prancing Pony Inn",
        "The tavern"
    ]
    if location not in valid_locations:
        raise ValueError(f"Invalid action: {location}. Valid options are: {', '.join(valid_locations)}")

    print("moving...")
    time.sleep(3)
    return f"You have arrived at {location}"

def routine(action: str) -> str:
    """
    You can choose to perform a certain action in your daily routine. Your ONLY options are as follows: clean prancing pony, open prancing pony, check on armory
    """
    valid_actions = [
        "wake up",
        "clean prancing pony",
        "open prancing pony",
        "check on armory"
    ]
    if action not in valid_actions:
        raise ValueError(f"Invalid action: {action}. Valid options are: {', '.join(valid_actions)}")
   
    print(f"acting... {action}")
    time.sleep(3)
    return f"You have completed {action}"