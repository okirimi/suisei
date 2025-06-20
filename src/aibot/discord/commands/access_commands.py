from discord import Interaction, SelectOption, User
from discord.ui import Select, View

from src.aibot.cli import logger
from src.aibot.discord.client import BotClient
from src.aibot.infrastructure.db.dao.access_dao import AccessLevelDAO
from src.aibot.json import get_text
from src.aibot.utils.decorators.access import is_admin_user, is_not_blocked_user

_client: BotClient = BotClient.get_instance()
access_dao = AccessLevelDAO()


async def _validate_guild_and_user(interaction: Interaction, user: User) -> tuple[bool, int]:
    """Validate that the command is run in a guild and the user exists in the guild.

    Parameters
    ----------
    interaction : Interaction
        The Discord interaction context.
    user : User
        The target Discord user to validate.

    Returns
    -------
    tuple[bool, int]
        A tuple containing:
        - bool: True if validation passed, False if failed
        - int: The user ID if validation passed, 0 if failed
    """
    target_user_id: int = user.id

    if interaction.guild is None:
        await interaction.response.send_message(
            get_text("access_control.guild_only_command"),
            ephemeral=True,
        )
        return False, 0

    target_user = interaction.guild.get_member(target_user_id)
    if target_user is None:
        await interaction.response.send_message(
            get_text("access_control.user_not_in_guild"),
            ephemeral=True,
        )
        return False, 0

    return True, target_user_id


class AccessLevelGrantSelector(Select):
    """Discord UI selector for granting access levels to users.

    This class creates a dropdown menu that allows administrators to
    select access levels ('advanced' or 'blocked') to grant to a user.

    Parameters
    ----------
    user_id : int
        The Discord user ID to grant access level to.
    options : list[SelectOption]
        List of SelectOption objects representing available access levels.
    """

    def __init__(self, user_id: int, options: list[SelectOption]) -> None:
        self.user_id = user_id
        super().__init__(
            placeholder=get_text(
                "access_control.select_access_level_placeholder",
            ),
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: Interaction) -> None:
        """Handle the user's selection of access level to grant.

        Parameters
        ----------
        interaction : Interaction
            The Discord interaction context.

        Notes
        -----
        This callback inserts the selected access level for the user into the database
        and sends a confirmation message.
        """
        chosen = self.values[0]  # "advanced" or "blocked"
        if chosen == "advanced":
            await access_dao.grant(user_id=self.user_id, access_level="advanced")
        elif chosen == "blocked":
            await access_dao.grant(user_id=self.user_id, access_level="blocked")

        await interaction.response.send_message(
            get_text(
                "access_control.access_level_granted",
                access_level=chosen,
                user_id=self.user_id,
            ),
            ephemeral=True,
        )
        logger.info(
            "Access level <%s> has been granted to the user (ID: %s)",
            chosen,
            self.user_id,
        )


class AccessLevelRevokeSelector(Select):
    """Discord UI selector for revoking access levels for users.

    This class creates a dropdown menu that allows administrators to
    select access levels ('advanced' or 'blocked') to revoke for a user.

    Parameters
    ----------
    user_id : int
        The Discord user ID to revoke access level for.
    options : list[SelectOption]
        List of SelectOption objects representing available access levels.
    """

    def __init__(self, user_id: int, options: list[SelectOption]) -> None:
        self.user_id = user_id
        super().__init__(
            placeholder=get_text(
                "access_control.select_access_level_placeholder",
            ),
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: Interaction) -> None:
        """Handle the user's selection of access level to revoke.

        Parameters
        ----------
        interaction : Interaction
            The Discord interaction context.

        Notes
        -----
        This callback revokes the selected access level for the user in the database
        and sends a confirmation message. If the user doesn't have the specified
        access level, it sends an informative message instead.
        """
        chosen = self.values[0]  # "advanced" or "blocked"

        # Check if the user currently has the selected access level
        user_ids_with_access = await access_dao.fetch_user_ids_by_access_level(chosen)

        if self.user_id not in user_ids_with_access:
            await interaction.response.send_message(
                get_text(
                    "access_control.user_does_not_have_access_level",
                    user_id=self.user_id,
                    access_level=chosen,
                ),
                ephemeral=True,
            )
            logger.info(
                "Attempted to revoke access level <%s> from user (ID: %s) but they don't have it",
                chosen,
                self.user_id,
            )
            return

        # User has the access level, proceed with revocation
        if chosen == "advanced":
            await access_dao.revoke(user_id=self.user_id, access_level="advanced")
        elif chosen == "blocked":
            await access_dao.revoke(user_id=self.user_id, access_level="blocked")

        await interaction.response.send_message(
            get_text(
                "access_control.access_level_revoked",
                access_level=chosen,
                user_id=self.user_id,
            ),
            ephemeral=True,
        )
        logger.info(
            "Access level <%s> has been revoked from the user (ID: %s)",
            chosen,
            self.user_id,
        )


@_client.tree.command(name="grant", description=get_text("commands.grant.description"))
@is_admin_user()
@is_not_blocked_user()
async def grant_command(interaction: Interaction, user: User) -> None:
    """Grant access level to a Discord user.

    Parameters
    ----------
    interaction : Interaction
        The Discord interaction context.
    user : User
        The target Discord user to grant access level to.

    Notes
    -----
    This function grants 'advanced' or 'blocked' access level to the specified user.
    """
    is_valid, target_user_id = await _validate_guild_and_user(interaction, user)
    if not is_valid:
        return

    options = [
        SelectOption(label="advanced", value="advanced"),
        SelectOption(label="blocked", value="blocked"),
    ]

    select = AccessLevelGrantSelector(user_id=target_user_id, options=options)
    view = View()
    view.add_item(select)

    await interaction.response.send_message(
        get_text("access_control.grant_access_level_message"),
        view=view,
        ephemeral=True,
    )


@_client.tree.command(name="check", description=get_text("commands.check.description"))
@is_admin_user()
@is_not_blocked_user()
async def check_access_command(interaction: Interaction, user: User) -> None:
    """Check the access level of a Discord user.

    Parameters
    ----------
    interaction : Interaction
        The Discord interaction context.
    user : User
        The target Discord user to check access level for.

    Notes
    -----
    This function displays whether the user has 'advanced' or 'blocked' access level.
    """
    is_valid, target_user_id = await _validate_guild_and_user(interaction, user)
    if not is_valid:
        return

    advanced_user_ids = await access_dao.fetch_user_ids_by_access_level("advanced")
    blocked_user_ids = await access_dao.fetch_user_ids_by_access_level("blocked")

    if target_user_id in advanced_user_ids and target_user_id in blocked_user_ids:
        await interaction.response.send_message(
            get_text(
                "access_control.user_has_advanced_and_blocked",
                user_id=target_user_id,
            ),
            ephemeral=True,
        )
        return
    if target_user_id in advanced_user_ids:
        await interaction.response.send_message(
            get_text(
                "access_control.user_has_advanced",
                user_id=target_user_id,
            ),
            ephemeral=True,
        )
        return
    if target_user_id in blocked_user_ids:
        await interaction.response.send_message(
            get_text(
                "access_control.user_has_blocked",
                user_id=target_user_id,
            ),
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        get_text(
            "access_control.user_has_no_access_level",
            user_id=target_user_id,
        ),
        ephemeral=True,
    )


@_client.tree.command(name="revoke", description=get_text("commands.revoke.description"))
@is_admin_user()
@is_not_blocked_user()
async def revoke_command(interaction: Interaction, user: User) -> None:
    """Revoke access level for a Discord user.

    Parameters
    ----------
    interaction : Interaction
        The Discord interaction context.
    user : User
        The target Discord user to revoke access level for.

    Notes
    -----
    This function revokes 'advanced' or 'blocked' access level for the specified user.
    """
    is_valid, target_user_id = await _validate_guild_and_user(interaction, user)
    if not is_valid:
        return

    options = [
        SelectOption(label="advanced", value="advanced"),
        SelectOption(label="blocked", value="blocked"),
    ]

    select = AccessLevelRevokeSelector(user_id=target_user_id, options=options)
    view = View()
    view.add_item(select)

    await interaction.response.send_message(
        get_text("access_control.revoke_access_level_message"),
        view=view,
        ephemeral=True,
    )
