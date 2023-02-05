import sqlite3
import time
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

import breadcord


class TagContentModal(discord.ui.Modal):
    content = discord.ui.TextInput(label="Tag Content", style=discord.TextStyle.long, min_length=1, max_length=2000)

    def __init__(self, *, default_content: str, edited: bool = False) -> None:
        self.title = "Edit tag" if edited else "Define new tag"
        super().__init__()
        self.text = None
        self.interaction = None
        self.content.default = default_content

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.text = str(self.content)
        self.interaction = interaction
        self.stop()


class Breadcrumbs(breadcord.module.ModuleCog, commands.GroupCog, name="tag"):
    def __init__(self, name: str | None = None) -> None:
        super().__init__(name)
        self.connection = sqlite3.connect(self.module.storage_path / "tags.db")
        self.cursor = self.connection.cursor()
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS tags ("
            "   tag_name TEXT NOT NULL,"
            "   tag_guild_id INTEGER NOT NULL,"
            "   tag_content TEXT NOT NULL,"
            "   last_edited_by INTEGER NOT NULL,"
            "   last_edited_at TIMESTAMP NOT NULL,"
            "   PRIMARY KEY (tag_name, tag_guild_id)"
            ")"
        )

    @app_commands.command(name="set", description="Set the content of a tag.")
    @app_commands.describe(tag_name="Tag name.")
    async def tag_set(self, interaction: discord.Interaction, tag_name: str):
        tag_name = tag_name.strip()
        last_edited_at = time.mktime(interaction.created_at.timetuple())

        old_value = self.cursor.execute(
            "SELECT tag_content FROM tags WHERE tag_name = ? AND tag_guild_id = ?",
            (tag_name, interaction.guild.id),
        ).fetchone()

        edited = old_value is not None
        modal = TagContentModal(default_content=old_value[0] if edited else "", edited=edited)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.cursor.execute(
            "DELETE FROM tags WHERE tag_name = ? AND tag_guild_id = ?", (tag_name, interaction.guild.id)
        )
        self.cursor.execute(
            "INSERT INTO tags VALUES (?, ?, ?, ?, ?)",
            (tag_name, interaction.guild.id, modal.text, interaction.user.id, last_edited_at),
        )
        self.connection.commit()
        await modal.interaction.response.send_message("Successfully saved tag.")

    async def tag_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        tags = self.cursor.execute(
            "SELECT tag_name FROM tags WHERE tag_guild_id = ? AND (tag_name LIKE ? OR ? = '')",
            (interaction.guild.id, f"%{current}%", current),
        ).fetchall()
        return [app_commands.Choice(name=tag[0], value=tag[0]) for tag in tags]

    @app_commands.command(name="get", description="Get the content of a tag")
    @app_commands.describe(tag="Name of the tag you want to get")
    @app_commands.autocomplete(tag=tag_autocomplete)  # type: ignore
    async def tag_get(self, interaction: discord.Interaction, tag: str):
        tag_content = self.cursor.execute(
            "SELECT tag_content FROM tags WHERE tag_name = ? AND tag_guild_id = ?",
            (tag.strip(), interaction.guild.id),
        ).fetchone()

        await interaction.response.send_message(
            tag_content[0] if tag_content is not None else "There's no tag with that name."
        )

    @app_commands.command(name="info", description="Get info about a tag")
    @app_commands.describe(tag="Name of the tag you want info about")
    @app_commands.autocomplete(tag=tag_autocomplete)  # type: ignore
    async def tag_info(self, interaction: discord.Interaction, tag: str):
        # noinspection PyTypeChecker
        tag_data = self.cursor.execute(
            "SELECT tag_name, tag_content, last_edited_by, last_edited_at FROM tags "
            "WHERE tag_name = ? AND tag_guild_id = ?",
            (tag.strip(), interaction.guild.id),
        ).fetchone()

        if tag_data is None:
            await interaction.response.send_message("There's no tag with that name.")
            return

        tag_name, tag_content, last_edited_by, last_edited_at = tag_data
        embed = discord.Embed(title=tag_name, description=tag_content, timestamp=datetime.fromtimestamp(last_edited_at))
        last_edited_by = await self.bot.fetch_user(last_edited_by)
        embed.set_footer(text=f"Last edited by: {last_edited_by.name}", icon_url=last_edited_by.display_avatar)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: breadcord.Bot):
    await bot.add_cog(Breadcrumbs())
